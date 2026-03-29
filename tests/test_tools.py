"""Tests for tool interface, registry, validation, and builtins."""

import hashlib
import json
import platform
import tempfile
from pathlib import Path

import pytest

from pantheon.tools import (
    ListDir,
    ReadFile,
    Registry,
    SearchFiles,
    WriteFile,
    _default_auditor,
    _get_last_hash,
    _validate_args,
    builtins,
    check_required,
    strict_schema,
    verify_audit_chain,
)
from tests.echo_tool import EchoTool


def _reset_auditor(monkeypatch, audit_path):
    """Reset audit singleton state for test isolation."""
    monkeypatch.setenv("PANTHEON_AUDIT_LOG_PATH", str(audit_path))
    _default_auditor.reset()


class TestRegistry:
    def test_register_and_get(self):
        r = Registry()
        r.register(EchoTool())
        tool = r.get("echo")
        assert tool is not None
        assert tool.name() == "echo"

    def test_get_missing(self):
        r = Registry()
        assert r.get("nope") is None

    def test_definitions(self):
        r = Registry()
        r.register(EchoTool())
        defs = r.definitions()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["strict"] is True
        assert defs[0]["function"]["parameters"]["additionalProperties"] is False

    def test_execute_success(self):
        r = Registry()
        r.register(EchoTool())
        result = r.execute("echo", '{"msg": "hello"}')
        assert result == "hello"

    def test_execute_unknown(self):
        r = Registry()
        result = r.execute("nope", "{}")
        assert "unknown tool" in result

    def test_execute_missing_required(self):
        r = Registry()
        r.register(EchoTool())
        result = r.execute("echo", "{}")
        assert "missing required" in result

    def test_execute_all(self):
        r = Registry()
        r.register(EchoTool())
        calls = [
            {"id": "c1", "function": {"name": "echo", "arguments": '{"msg": "a"}'}},
            {"id": "c2", "function": {"name": "echo", "arguments": '{"msg": "b"}'}},
        ]
        results = r.execute_all(calls)
        assert len(results) == 2
        assert results[0]["content"] == "a"
        assert results[1]["content"] == "b"
        assert results[0]["role"] == "tool"
        assert results[0]["tool_call_id"] == "c1"

    def test_lazy_audit_log_and_redaction(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "tool-calls.jsonl"
        _reset_auditor(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())

        assert not audit_path.exists()
        r.execute("echo", '{"msg": "hello"}')
        assert audit_path.exists()

        entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
        assert entry["tool"] == "echo"
        assert entry["args"]["msg"] == "hello"
        assert entry["result_preview"] == "hello"

    def test_write_file_audit_redacts_content(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "tool-calls.jsonl"
        _reset_auditor(monkeypatch, audit_path)

        r = Registry()
        r.register(WriteFile())
        target = tmp_path / "secret.txt"
        r.execute(
            "write_file",
            json.dumps({"path": str(target), "content": "super-secret-value"}),
        )

        raw = audit_path.read_text(encoding="utf-8")
        entry = json.loads(raw.strip())
        assert "super-secret-value" not in raw
        assert entry["args"]["content"].startswith("[redacted content")
        assert entry["result_preview"] == "[redacted]"

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix-specific path /proc/1/")
    def test_audit_log_failure_does_not_break_tool_execution(self, monkeypatch, caplog):
        _reset_auditor(monkeypatch, Path("/proc/1/tool-calls.jsonl"))

        r = Registry()
        r.register(EchoTool())

        with caplog.at_level("WARNING"):
            result = r.execute("echo", '{"msg": "hello"}')

        assert result == "hello"
        assert "audit logging unavailable" in caplog.text


class TestCheckRequired:
    def test_all_present(self):
        schema = {"required": ["a", "b"]}
        assert check_required(schema, {"a": 1, "b": 2}) == []

    def test_missing(self):
        schema = {"required": ["a", "b"]}
        assert check_required(schema, {"a": 1}) == ["b"]

    def test_null_value(self):
        schema = {"required": ["a"]}
        assert check_required(schema, {"a": None}) == ["a"]

    def test_no_required(self):
        assert check_required({}, {"anything": True}) == []


class TestStrictSchema:
    def test_structure(self):
        s = strict_schema({"name": {"type": "string"}}, ["name"])
        assert s["type"] == "object"
        assert s["additionalProperties"] is False
        assert s["required"] == ["name"]
        assert "name" in s["properties"]


class TestBuiltinTools:
    def test_registry_has_all(self):
        r = builtins()
        expected = ["shell_exec", "read_file", "write_file", "list_dir", "search_files"]
        for name in expected:
            assert r.get(name) is not None, f"missing builtin: {name}"

    def test_read_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            tool = ReadFile()
            result = tool.execute({"path": path})
            assert result == "hello world"
        finally:
            Path(path).unlink()

    def test_read_file_missing(self):
        tool = ReadFile()
        result = tool.execute({"path": "/nonexistent/path/file.txt"})
        assert "error" in result

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "sub" / "test.txt")
            tool = WriteFile()
            result = tool.execute({"path": path, "content": "test data"})
            assert "wrote" in result
            assert Path(path).read_text() == "test data"

    def test_list_dir(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "file.txt").write_text("x")
            (Path(d) / "subdir").mkdir()
            tool = ListDir()
            result = tool.execute({"path": d})
            assert "file.txt" in result
            assert "subdir/" in result


class TestPathRestrictions:
    def test_read_file_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ok.txt"
            f.write_text("allowed")
            tool = ReadFile(allowed_roots=[d])
            assert tool.execute({"path": str(f)}) == "allowed"

    def test_read_file_blocked(self):
        with tempfile.TemporaryDirectory() as allowed:
            with tempfile.TemporaryDirectory() as blocked:
                f = Path(blocked) / "secret.txt"
                f.write_text("secret")
                tool = ReadFile(allowed_roots=[allowed])
                result = tool.execute({"path": str(f)})
                assert "outside allowed roots" in result

    def test_write_file_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.txt")
            tool = WriteFile(allowed_roots=[d])
            result = tool.execute({"path": path, "content": "ok"})
            assert "wrote" in result

    def test_write_file_blocked(self):
        with tempfile.TemporaryDirectory() as allowed:
            with tempfile.TemporaryDirectory() as blocked:
                path = str(Path(blocked) / "hack.txt")
                tool = WriteFile(allowed_roots=[allowed])
                result = tool.execute({"path": path, "content": "nope"})
                assert "outside allowed roots" in result
                assert not Path(path).exists()

    def test_no_restriction_allows_all(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("free")
            path = f.name
        try:
            assert ReadFile().execute({"path": path}) == "free"
        finally:
            Path(path).unlink()

    def test_search_files_filters_matches_outside_allowed_root(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        sibling = tmp_path / "sibling.txt"
        sibling.write_text("secret")

        tool = SearchFiles(allowed_roots=[allowed])
        result = tool.execute({"root": str(allowed), "pattern": "../*"})

        assert "pattern may not contain '..'" in result


class TestValidateArgs:
    def test_rejects_unexpected_arguments(self):
        schema = strict_schema(
            {"name": {"type": "string", "description": "Name"}},
            ["name"],
        )
        err = _validate_args(schema, {"name": "ok", "extra": "bad"})
        assert err is not None
        assert "unexpected arguments" in err
        assert "extra" in err

    def test_rejects_wrong_type(self):
        schema = strict_schema(
            {"count": {"type": "integer", "description": "Count"}},
            ["count"],
        )
        err = _validate_args(schema, {"count": "not-an-int"})
        assert err is not None
        assert "must be integer" in err

    def test_rejects_bool_for_string(self):
        schema = strict_schema(
            {"name": {"type": "string", "description": "Name"}},
            ["name"],
        )
        err = _validate_args(schema, {"name": True})
        assert err is not None
        assert "must be string" in err

    def test_accepts_valid_arguments(self):
        schema = strict_schema(
            {
                "name": {"type": "string", "description": "Name"},
                "count": {"type": "integer", "description": "Count"},
            },
            ["name", "count"],
        )
        err = _validate_args(schema, {"name": "hello", "count": 5})
        assert err is None

    def test_accepts_number_for_int_and_float(self):
        schema = strict_schema(
            {"value": {"type": "number", "description": "Value"}},
            ["value"],
        )
        assert _validate_args(schema, {"value": 42}) is None
        assert _validate_args(schema, {"value": 3.14}) is None

    def test_allows_additional_when_not_strict(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        err = _validate_args(schema, {"name": "ok", "extra": "fine"})
        assert err is None

    def test_registry_rejects_unexpected_args(self):
        r = Registry()
        r.register(EchoTool())
        result = r.execute("echo", '{"msg": "hi", "extra": "bad"}')
        assert "unexpected arguments" in result

    def test_registry_rejects_wrong_type(self):
        r = Registry()
        r.register(EchoTool())
        result = r.execute("echo", '{"msg": 42}')
        assert "must be string" in result


class TestAuditChainIntegrity:
    """Thread E: chained hashing for audit trail integrity."""

    def _reset_audit(self, monkeypatch, audit_path):
        _reset_auditor(monkeypatch, audit_path)

    def test_chain_genesis(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "first"}')

        entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
        assert entry["prev_hash"] == "genesis"
        assert "chain_hash" in entry

    def test_chain_links(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "first"}')
        r.execute("echo", '{"msg": "second"}')

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])

        assert entry1["prev_hash"] == "genesis"
        assert entry2["prev_hash"] == entry1["chain_hash"]

    def test_chain_hash_is_verifiable(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "verify-me"}')

        entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
        stored_hash = entry.pop("chain_hash")
        chain_input = f"{entry['prev_hash']}:{json.dumps(entry, sort_keys=True, default=str)}"
        expected = hashlib.sha256(chain_input.encode()).hexdigest()
        assert stored_hash == expected

    def test_tamper_detection(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "original"}')

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        entry = json.loads(lines[0])
        original_chain_hash = entry["chain_hash"]

        entry["tool"] = "tampered"
        entry.pop("chain_hash")
        chain_input = f"{entry['prev_hash']}:{json.dumps(entry, sort_keys=True, default=str)}"
        recomputed = hashlib.sha256(chain_input.encode()).hexdigest()
        assert recomputed != original_chain_hash

    def test_get_last_hash_empty_file(self, tmp_path):
        assert _get_last_hash(tmp_path / "nonexistent.jsonl") == "genesis"

    def test_get_last_hash_corrupted(self, tmp_path):
        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text("not valid json\n")
        assert _get_last_hash(bad_file) == "genesis"

    def test_concurrent_writes_preserve_chain(self, tmp_path, monkeypatch):
        """Verify the threading lock prevents forked chains under execute_all."""
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        calls = [
            {
                "id": f"c{i}",
                "function": {"name": "echo", "arguments": json.dumps({"msg": f"m{i}"})},
            }
            for i in range(4)
        ]
        r.execute_all(calls)

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 4

        prev = "genesis"
        for line in lines:
            entry = json.loads(line)
            assert entry["prev_hash"] == prev
            prev = entry["chain_hash"]


class TestAuditVerify:
    """Tests for verify_audit_chain()."""

    def _reset_audit(self, monkeypatch, audit_path):
        _reset_auditor(monkeypatch, audit_path)

    def test_audit_verify_intact_chain(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "first"}')
        r.execute("echo", '{"msg": "second"}')
        r.execute("echo", '{"msg": "third"}')

        valid, issues = verify_audit_chain(audit_path)
        assert valid is True
        assert issues == []

    def test_audit_verify_detects_tampered_entry(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "first"}')
        r.execute("echo", '{"msg": "second"}')
        r.execute("echo", '{"msg": "third"}')

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        entry = json.loads(lines[1])
        entry["tool"] = "tampered"
        lines[1] = json.dumps(entry, separators=(",", ":"))
        audit_path.write_text("\n".join(lines) + "\n")

        valid, issues = verify_audit_chain(audit_path)
        assert valid is False
        assert any("chain_hash mismatch" in i for i in issues)

    def test_audit_verify_detects_deleted_entry(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        self._reset_audit(monkeypatch, audit_path)

        r = Registry()
        r.register(EchoTool())
        r.execute("echo", '{"msg": "first"}')
        r.execute("echo", '{"msg": "second"}')
        r.execute("echo", '{"msg": "third"}')

        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        del lines[1]
        audit_path.write_text("\n".join(lines) + "\n")

        valid, issues = verify_audit_chain(audit_path)
        assert valid is False
        assert any("prev_hash mismatch" in i for i in issues)

    def test_audit_verify_empty_log(self, tmp_path):
        valid, issues = verify_audit_chain(tmp_path / "nonexistent.jsonl")
        assert valid is True
        assert len(issues) == 1
        assert "not found" in issues[0]


class TestSensitiveFileProtection:
    """Thread C: ReadFile blocks access to secrets files (.env)."""

    def test_read_file_blocks_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=value")
        tool = ReadFile()
        result = tool.execute({"path": str(env_file)})
        assert "blocked" in result
        assert "secrets" in result

    def test_read_file_blocks_env_local(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("SECRET=value")
        tool = ReadFile()
        result = tool.execute({"path": str(env_file)})
        assert "blocked" in result

    def test_read_file_blocks_env_production(self, tmp_path):
        env_file = tmp_path / ".env.production"
        env_file.write_text("SECRET=value")
        tool = ReadFile()
        result = tool.execute({"path": str(env_file)})
        assert "blocked" in result

    def test_read_file_blocks_env_staging(self, tmp_path):
        env_file = tmp_path / ".env.staging"
        env_file.write_text("SECRET=value")
        tool = ReadFile()
        result = tool.execute({"path": str(env_file)})
        assert "blocked" in result

    def test_read_file_allows_env_example(self, tmp_path):
        env_file = tmp_path / ".env.example"
        env_file.write_text("KEY=placeholder")
        tool = ReadFile()
        result = tool.execute({"path": str(env_file)})
        assert "blocked" not in result
        assert "KEY=placeholder" in result

    def test_read_file_allows_regular_files(self, tmp_path):
        regular = tmp_path / "config.yaml"
        regular.write_text("key: value")
        tool = ReadFile()
        result = tool.execute({"path": str(regular)})
        assert result == "key: value"


class TestWriteFileSensitive:
    """WriteFile blocks writes to secrets files (.env) — parity with ReadFile."""

    def test_blocks_env_write(self, tmp_path):
        wf = WriteFile(allowed_roots=[tmp_path])
        result = wf.execute({"path": str(tmp_path / ".env"), "content": "LEAKED=1"})
        assert "blocked" in result
        assert not (tmp_path / ".env").exists()

    def test_allows_env_example_write(self, tmp_path):
        wf = WriteFile(allowed_roots=[tmp_path])
        result = wf.execute({"path": str(tmp_path / ".env.example"), "content": "KEY="})
        assert "wrote" in result

    def test_blocks_env_local_write(self, tmp_path):
        wf = WriteFile(allowed_roots=[tmp_path])
        result = wf.execute({"path": str(tmp_path / ".env.local"), "content": "X=1"})
        assert "blocked" in result
        assert not (tmp_path / ".env.local").exists()
