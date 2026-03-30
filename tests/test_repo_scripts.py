"""Tests for repository utility scripts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REPO_ROOT = Path(__file__).resolve().parents[1]

doctor = _load_module("pantheon_doctor", "scripts/doctor.py")
secret_scan = _load_module("pantheon_secret_scan", "scripts/secret_scan.py")
skill_validate = _load_module("pantheon_skill_validate", "scripts/skill_validate.py")


class TestDoctor:
    def test_repo_root(self, tmp_path):
        from pantheon.config import repo_root

        root = tmp_path / "repo"
        nested = root / "nested" / "dir"
        (root / ".agents" / "skills").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        nested.mkdir(parents=True)

        assert repo_root(nested) == root

    def test_doctor_claude_code_runs(self, tmp_path):
        """Verify doctor claude-code subcommand produces structured output."""
        root = tmp_path / "repo"
        (root / ".agents" / "skills").mkdir(parents=True)
        (root / ".agents" / "subagents").mkdir(parents=True)
        (root / "src" / "pantheon").mkdir(parents=True)
        (root / "src" / "pantheon" / "__init__.py").write_text("__version__ = '0.0.0'\n")
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        (root / "CLAUDE.md").write_text("## Bootstrap\nActivation rule.\n")
        (root / "AGENTS.md").write_text("## Roster\n| Agent |\n|-------|\n| demeter |\n")

        results = doctor.check_claude_code(root)

        assert len(results) >= 6
        statuses = {r.name: r.status for r in results}
        assert statuses["claude-md"] == "ok"
        assert statuses["agents-md"] == "ok"
        assert statuses["pantheon-source"] == "ok"
        assert statuses["no-cursor-deps"] == "ok"
        assert statuses["skills"] == "fail"
        assert statuses["subagents"] == "fail"

    def test_doctor_claude_code_detects_cursor_refs(self, tmp_path):
        """doctor claude-code should warn when SKILL.md files reference Cursor."""
        root = tmp_path / "repo"
        (root / ".agents" / "skills" / "clean_skill").mkdir(parents=True)
        (root / ".agents" / "skills" / "cursor_skill").mkdir(parents=True)
        (root / ".agents" / "subagents").mkdir(parents=True)
        (root / "src" / "pantheon").mkdir(parents=True)
        (root / "src" / "pantheon" / "__init__.py").write_text("__version__ = '0.0.0'\n")
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        (root / "CLAUDE.md").write_text("## Bootstrap\nActivation rule.\n")
        (root / "AGENTS.md").write_text("## Roster\n| Agent |\n|-------|\n| demeter |\n")

        (root / ".agents" / "skills" / "clean_skill" / "SKILL.md").write_text(
            "---\nname: clean\ndescription: no cursor refs\n---\nPortable skill.\n"
        )
        (root / ".agents" / "skills" / "cursor_skill" / "SKILL.md").write_text(
            "---\nname: cursor\ndescription: has cursor refs\n---\nIn Cursor, use MCP.\n"
        )

        results = doctor.check_claude_code(root)
        statuses = {r.name: r.status for r in results}
        details = {r.name: r.detail for r in results}

        assert statuses["no-cursor-deps"] == "warn"
        assert "cursor_skill" in details["no-cursor-deps"]
        assert "clean_skill" not in details["no-cursor-deps"]

    def test_doctor_claude_code_ok_without_cursor_refs(self, tmp_path):
        """doctor claude-code should pass when no SKILL.md files reference Cursor."""
        root = tmp_path / "repo"
        (root / ".agents" / "skills" / "portable_skill").mkdir(parents=True)
        (root / ".agents" / "subagents").mkdir(parents=True)
        (root / "src" / "pantheon").mkdir(parents=True)
        (root / "src" / "pantheon" / "__init__.py").write_text("__version__ = '0.0.0'\n")
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        (root / "CLAUDE.md").write_text("## Bootstrap\nActivation rule.\n")
        (root / "AGENTS.md").write_text("## Roster\n| Agent |\n|-------|\n| demeter |\n")

        (root / ".agents" / "skills" / "portable_skill" / "SKILL.md").write_text(
            "---\nname: portable\ndescription: clean\n---\nNo cursor references here.\n"
        )

        results = doctor.check_claude_code(root)
        statuses = {r.name: r.status for r in results}
        details = {r.name: r.detail for r in results}

        assert statuses["no-cursor-deps"] == "ok"
        assert "No Cursor-specific references" in details["no-cursor-deps"]


class TestSecretScan:
    def test_finds_secrets_with_redacted_preview(self, tmp_path):
        target = tmp_path / "config.env"
        target.write_text("GITLAB_PERSONAL_ACCESS_TOKEN=glpat-1234567890abcdefghijklmnop\n")

        findings = secret_scan.scan_tree(tmp_path, excludes=set())

        assert len(findings) == 2
        assert all("1234567890abcdefghijklmnop" not in finding.preview for finding in findings)

    def test_respects_excludes(self, tmp_path):
        excluded = tmp_path / "ignore-me"
        excluded.mkdir()
        (excluded / "secret.txt").write_text("token=supersecrettokenvalue\n")

        findings = secret_scan.scan_tree(tmp_path, excludes={"ignore-me"})

        assert findings == []

    def test_skips_binary_files(self, tmp_path):
        binary = tmp_path / "blob.bin"
        binary.write_bytes(b"\x00\x01\x02glpat-1234567890abcdefghijklmnop")

        findings = secret_scan.scan_tree(tmp_path, excludes=set())

        assert findings == []


class TestSubagentSync:
    def test_subagent_definitions_in_sync(self):
        """Portable and Cursor subagent definitions should cover the same agents."""
        portable = set(p.stem for p in (REPO_ROOT / ".agents" / "subagents").glob("*.md"))
        cursor = set(p.stem for p in (REPO_ROOT / ".cursor" / "agents").glob("*.md"))
        assert portable == cursor, (
            f"Drift detected: portable_only={portable - cursor}, cursor_only={cursor - portable}"
        )

    def test_portable_versions_have_no_cursor_references(self):
        """Portable subagent definitions should not reference .cursor/mcp.json."""
        for path in (REPO_ROOT / ".agents" / "subagents").glob("*.md"):
            content = path.read_text(encoding="utf-8")
            assert ".cursor/mcp.json" not in content, f"{path.name} has Cursor-specific reference"


class TestSkillValidate:
    def test_validation_warns_on_missing_eval_but_has_no_errors(self, tmp_path):
        root = tmp_path / "repo"
        (root / ".agents" / "skills" / "athena").mkdir(parents=True)
        (root / ".agents" / "skills" / "demeter").mkdir(parents=True)
        (root / ".agents" / "skills" / "athena" / "SKILL.md").write_text(
            "---\ndescription: x\n---\n"
        )
        (root / ".agents" / "skills" / "demeter" / "SKILL.md").write_text(
            "---\ndescription: x\n---\n"
        )
        (root / ".cursor" / "rules").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "evals" / "athena").mkdir(parents=True)
        (root / "evals" / "athena" / "eval.yaml").write_text("version: '1'\n")
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        (root / "scripts" / "helper.py").write_text("print('ok')\n")
        (root / "scripts" / "README.md").write_text("- `helper.py`\n")
        (root / "README.md").write_text(
            "## The Pantheon\n\n| Name | Persona |\n"
            "|------|---------|\n| athena | x |\n| demeter | x |\n"
        )
        (root / "AGENTS.md").write_text(
            "## Roster\n\n| Agent | Persona |\n"
            "|-------|---------|\n| athena | x |\n| demeter | x |\n"
        )
        (root / ".cursor" / "rules" / "pantheon.mdc").write_text(
            "## Roster\n\n| Agent | Role |\n|-------|------|\n| athena | x |\n| demeter | x |\n"
        )

        findings = skill_validate.run_validation(root)
        levels = [finding.level for finding in findings]

        assert "error" not in levels
        assert any(
            "skills without eval coverage: demeter" in finding.message for finding in findings
        )
