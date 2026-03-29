"""Shared configuration — single source for path resolution and env loading."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

_KNOWN_ENV_VARS = {
    "AGENTS_DIR",
    "ANTHROPIC_API_KEY",
    "API_KEY",
    "GATEWAY_URL",
    "GEMINI_API_KEY",
    "INFERENCE_API_KEY",
    "INFERENCE_RATE_LIMIT_DISABLE",
    "INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN",
    "INFERENCE_RATE_LIMIT_PER_DAY",
    "INFERENCE_RATE_LIMIT_PER_HOUR",
    "INFERENCE_RATE_LIMIT_PER_MINUTE",
    "INFERENCE_RATE_LIMIT_PER_SECOND",
    "INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS",
    "INFERENCE_RATE_LIMIT_STATE_DIR",
    "MEMORY_DIR",
    "NIM_API_KEY",
    "NIM_BASE_URL",
    "NIM_MODEL",
    "OPENAI_API_KEY",
    "PANTHEON_AUDIT_LOG_PATH",
    "SHELL_EXEC_ALLOW_LIST",
    "SHELL_EXEC_MODE",
    "SHELL_EXEC_TIMEOUT",
    "SKILLS_DIR",
    "VERBOSE",
}

_BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent / "_bundled_skills"


def repo_root(start: str | Path | None = None) -> Path | None:
    """Return the Pantheon repository root when it can be discovered."""
    starts = [Path(start)] if start is not None else [Path.cwd(), Path(__file__)]
    seen: set[Path] = set()

    for base in starts:
        current = base.resolve()
        if current.is_file():
            current = current.parent

        for candidate in (current, *current.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "pyproject.toml").exists() and (
                candidate / ".agents" / "skills"
            ).is_dir():
                return candidate

    return None


def _resolve_env_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p

    if root := repo_root(Path.cwd()):
        candidate = root / p
        if candidate.exists():
            return candidate

    return p


def parse_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Parse a .env file and return key-value pairs as a dict.

    Skips comments and blank lines, strips surrounding quotes.
    Does not filter by _KNOWN_ENV_VARS and does not mutate os.environ.
    """
    p = _resolve_env_path(path)
    if not p.exists():
        return {}
    result: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def load_env(path: str = ".env") -> None:
    """Load known env vars from .env without overwriting existing values."""
    for key, value in parse_env_file(path).items():
        if key in _KNOWN_ENV_VARS and not os.environ.get(key):
            os.environ[key] = value


def skills_dir() -> str:
    for var in ("SKILLS_DIR", "AGENTS_DIR"):
        if d := os.environ.get(var):
            return d
    for candidate in (".agents/skills", ".cursor/skills", ".claude/skills"):
        if Path(candidate).is_dir():
            return candidate
    if root := repo_root(Path.cwd()):
        for candidate in (".agents/skills", ".cursor/skills", ".claude/skills"):
            resolved = root / candidate
            if resolved.is_dir():
                return str(resolved)
    if _BUNDLED_SKILLS_DIR.is_dir():
        return str(_BUNDLED_SKILLS_DIR)
    if root := repo_root(Path.cwd()):
        return str(root / ".agents/skills")
    return ".agents/skills"


_SK_PREFIX_RULES: list[tuple[tuple[str, ...], str]] = [
    (("bedrock-claude",), "aws/anthropic/"),
    (("claude-",), "azure/anthropic/"),
    (("gpt-", "o1", "o3", "o4", "text-embedding"), "azure/openai/"),
    (("gemini-",), "gcp/google/"),
    (("sonar",), "perplexity/perplexity/"),
]

_SK_FALLBACK_MODEL = "azure/openai/gpt-4.1-mini"


def resolve_model(model: str, key: str | None = None) -> str:
    """Resolve a model name for the active API key.

    nvapi- keys use short LiteLLM proxy aliases (e.g. ``gpt-5.3-codex``).
    sk- keys require the full provider-prefixed name
    (e.g. ``azure/openai/gpt-5.3-codex``).  When an sk- key is active
    and the model lacks a provider prefix, the correct prefix is inferred
    from the model name.
    """
    effective_key = key if key is not None else api_key()
    if not effective_key.startswith("sk-"):
        return model
    if "/" in model:
        return model
    for prefixes, provider in _SK_PREFIX_RULES:
        if any(model.startswith(p) for p in prefixes):
            return f"{provider}{model}"
    return _SK_FALLBACK_MODEL


def gateway_url() -> str:
    if u := os.environ.get("GATEWAY_URL"):
        return _validate_gateway_url(u)
    raise RuntimeError(
        "GATEWAY_URL environment variable is required. "
        "Set it to your OpenAI-compatible inference endpoint (e.g. https://api.openai.com/v1)."
    )


def api_key() -> str:
    for var in ("INFERENCE_API_KEY", "API_KEY", "ANTHROPIC_API_KEY"):
        if k := os.environ.get(var):
            return k
    return ""


def memory_dir() -> str:
    return os.environ.get("MEMORY_DIR", ".memory")


def verbose() -> bool:
    return os.environ.get("VERBOSE", "") in ("1", "true")


def _validate_gateway_url(url: str) -> str:
    """Normalize and validate an OpenAI-compatible base URL."""
    parsed = urlparse(url.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid gateway URL: {url}")
    if parsed.scheme != "https" and parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("gateway URL must use https unless it targets localhost/loopback")
    return url.rstrip("/")
