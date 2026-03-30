"""Tests for configuration — env loading, directory discovery, defaults."""

import os
from unittest.mock import patch

import pytest

import pantheon.config as config_mod
from pantheon.config import (
    api_key,
    gateway_url,
    load_env,
    memory_dir,
    repo_root,
    resolve_model,
    skills_dir,
    verbose,
)


class TestLoadEnv:
    def test_loads_from_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MEMORY_DIR=.memory-test\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MEMORY_DIR", None)
            load_env(str(env_file))
            assert os.environ["MEMORY_DIR"] == ".memory-test"
            del os.environ["MEMORY_DIR"]

    def test_skips_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nVERBOSE=true\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERBOSE", None)
            load_env(str(env_file))
            assert os.environ["VERBOSE"] == "true"
            del os.environ["VERBOSE"]

    def test_does_not_override_existing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MEMORY_DIR=new\n")

        with patch.dict(os.environ, {"MEMORY_DIR": "existing"}, clear=False):
            load_env(str(env_file))
            assert os.environ["MEMORY_DIR"] == "existing"

    def test_missing_file_is_noop(self):
        load_env("/nonexistent/.env")

    def test_loads_repo_root_env_from_subdirectory(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        subdir = root / "nested" / "work"
        (root / ".agents" / "skills").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        (root / ".env").write_text("MEMORY_DIR=.memory-root\n")
        subdir.mkdir(parents=True)

        monkeypatch.chdir(subdir)
        monkeypatch.delenv("MEMORY_DIR", raising=False)

        load_env()

        assert os.environ["MEMORY_DIR"] == ".memory-root"
        del os.environ["MEMORY_DIR"]

    def test_strips_double_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('MEMORY_DIR="hello world"\n')

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MEMORY_DIR", None)
            load_env(str(env_file))
            assert os.environ["MEMORY_DIR"] == "hello world"
            del os.environ["MEMORY_DIR"]

    def test_strips_single_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MEMORY_DIR='single'\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MEMORY_DIR", None)
            load_env(str(env_file))
            assert os.environ["MEMORY_DIR"] == "single"
            del os.environ["MEMORY_DIR"]

    def test_handles_values_with_equals(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GATEWAY_URL=http://localhost:8080/v1?a=1&b=2\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GATEWAY_URL", None)
            load_env(str(env_file))
            assert os.environ["GATEWAY_URL"] == "http://localhost:8080/v1?a=1&b=2"
            del os.environ["GATEWAY_URL"]

    def test_ignores_unknown_keys(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_PANTHEON_VAR=hello\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_PANTHEON_VAR", None)
            load_env(str(env_file))
            assert "TEST_PANTHEON_VAR" not in os.environ

    def test_loads_audit_log_path(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PANTHEON_AUDIT_LOG_PATH=.audit/custom.jsonl\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PANTHEON_AUDIT_LOG_PATH", None)
            load_env(str(env_file))
            assert os.environ["PANTHEON_AUDIT_LOG_PATH"] == ".audit/custom.jsonl"
            del os.environ["PANTHEON_AUDIT_LOG_PATH"]

    def test_loads_inference_rate_limit_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("INFERENCE_RATE_LIMIT_PER_SECOND=4\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INFERENCE_RATE_LIMIT_PER_SECOND", None)
            load_env(str(env_file))
            assert os.environ["INFERENCE_RATE_LIMIT_PER_SECOND"] == "4"
            del os.environ["INFERENCE_RATE_LIMIT_PER_SECOND"]


class TestSkillsDir:
    def test_env_override(self):
        with patch.dict(os.environ, {"SKILLS_DIR": "/custom/skills"}):
            assert skills_dir() == "/custom/skills"

    def test_agents_dir_fallback(self):
        with patch.dict(os.environ, {"AGENTS_DIR": "/agents"}, clear=False):
            os.environ.pop("SKILLS_DIR", None)
            assert skills_dir() == "/agents"

    def test_default_when_no_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SKILLS_DIR", raising=False)
        monkeypatch.delenv("AGENTS_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        assert skills_dir() == ".agents/skills"

    def test_bundled_skills_fallback(self, tmp_path, monkeypatch):
        bundled = tmp_path / "_bundled_skills"
        bundled.mkdir()
        monkeypatch.delenv("SKILLS_DIR", raising=False)
        monkeypatch.delenv("AGENTS_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(config_mod, "_BUNDLED_SKILLS_DIR", bundled)
        assert skills_dir() == str(bundled)

    def test_repo_root_fallback(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        nested = root / "nested" / "dir"
        (root / ".agents" / "skills").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")
        nested.mkdir(parents=True)

        monkeypatch.delenv("SKILLS_DIR", raising=False)
        monkeypatch.delenv("AGENTS_DIR", raising=False)
        monkeypatch.chdir(nested)

        assert skills_dir() == str(root / ".agents" / "skills")


class TestGatewayUrl:
    def test_env_override(self):
        with patch.dict(os.environ, {"GATEWAY_URL": "https://custom/v1/"}):
            assert gateway_url() == "https://custom/v1"

    def test_raises_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GATEWAY_URL", None)
            with pytest.raises(RuntimeError, match="GATEWAY_URL environment variable is required"):
                gateway_url()

    def test_allows_local_http(self):
        with patch.dict(os.environ, {"GATEWAY_URL": "http://localhost:8080/v1"}):
            assert gateway_url() == "http://localhost:8080/v1"

    def test_rejects_invalid_gateway_url(self):
        with (
            patch.dict(os.environ, {"GATEWAY_URL": "not-a-url"}),
            pytest.raises(ValueError, match="invalid gateway URL"),
        ):
            gateway_url()


class TestApiKey:
    def test_inference_api_key_precedence(self):
        with patch.dict(
            os.environ,
            {
                "INFERENCE_API_KEY": "inference-secret",
                "API_KEY": "secret",
            },
        ):
            assert api_key() == "inference-secret"

    def test_env_override(self):
        with patch.dict(os.environ, {"API_KEY": "secret"}, clear=False):
            os.environ.pop("INFERENCE_API_KEY", None)
            assert api_key() == "secret"

    def test_default_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INFERENCE_API_KEY", None)
            os.environ.pop("API_KEY", None)
            assert api_key() == ""


class TestResolveModel:
    def test_nvapi_key_passes_through(self):
        with patch.dict(os.environ, {"INFERENCE_API_KEY": "nvapi-test"}, clear=False):
            assert resolve_model("bedrock-claude-opus-4-6") == "bedrock-claude-opus-4-6"

    def test_sk_key_maps_proxy_alias(self):
        with patch.dict(os.environ, {"INFERENCE_API_KEY": "sk-test"}, clear=False):
            os.environ.pop("API_KEY", None)
            assert (
                resolve_model("bedrock-claude-opus-4-6") == "aws/anthropic/bedrock-claude-opus-4-6"
            )

    def test_sk_key_maps_gpt_alias(self):
        with patch.dict(os.environ, {"INFERENCE_API_KEY": "sk-test"}, clear=False):
            os.environ.pop("API_KEY", None)
            assert resolve_model("gpt-5.3-codex") == "azure/openai/gpt-5.3-codex"

    def test_sk_key_passes_prefixed_models_through(self):
        with patch.dict(os.environ, {"INFERENCE_API_KEY": "sk-test"}, clear=False):
            os.environ.pop("API_KEY", None)
            assert resolve_model("azure/openai/gpt-5.3-codex") == "azure/openai/gpt-5.3-codex"

    def test_sk_key_unknown_model_gets_fallback(self):
        with patch.dict(os.environ, {"INFERENCE_API_KEY": "sk-test"}, clear=False):
            os.environ.pop("API_KEY", None)
            result = resolve_model("unknown-model-xyz")
            assert "/" in result


class TestMemoryDir:
    def test_env_override(self):
        with patch.dict(os.environ, {"MEMORY_DIR": "/custom/mem"}):
            assert memory_dir() == "/custom/mem"

    def test_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MEMORY_DIR", None)
            assert memory_dir() == ".memory"


class TestVerbose:
    def test_true_values(self):
        with patch.dict(os.environ, {"VERBOSE": "1"}):
            assert verbose() is True
        with patch.dict(os.environ, {"VERBOSE": "true"}):
            assert verbose() is True

    def test_false_values(self):
        with patch.dict(os.environ, {"VERBOSE": ""}):
            assert verbose() is False
        with patch.dict(os.environ, {"VERBOSE": "0"}):
            assert verbose() is False

    def test_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERBOSE", None)
            assert verbose() is False


class TestRepoRoot:
    def test_finds_repo_root_from_file(self, tmp_path):
        root = tmp_path / "repo"
        skill_file = root / ".agents" / "skills" / "athena" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text("---\ndescription: x\n---\n")
        (root / "pyproject.toml").write_text("[project]\nname='pantheon'\n")

        assert repo_root(skill_file) == root

    def test_returns_none_when_no_repo_root_exists(self, tmp_path):
        assert repo_root(tmp_path / "nowhere") is None
