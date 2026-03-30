"""Audit logging with chained integrity hashing."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import platform
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SENSITIVE_ARG_MARKERS = ("api", "auth", "key", "password", "secret", "token")
_REDACTED_OUTPUT_TOOLS = {"read_file", "search_files", "shell_exec", "write_file"}


class AuditLogger:
    """Encapsulates audit log state — replaces the former module-level globals."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("pantheon.audit")
        self._handler: logging.Handler | None = None
        self._path: Path | None = None
        self._lock = threading.Lock()
        self._last_chain_hash: str | None = None

    def setup(self, path: str | Path = ".audit/tool-calls.jsonl") -> None:
        """Configure the audit logger to write JSON lines to a file."""
        target = Path(os.environ.get("PANTHEON_AUDIT_LOG_PATH", str(path)))
        if self._handler is not None and self._path == target:
            return

        if self._handler is not None:
            self._logger.removeHandler(self._handler)
            self._handler.close()

        self._last_chain_hash = None

        p = target
        p.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(p, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._handler = handler
        self._path = p

        if platform.system() != "Windows":
            with contextlib.suppress(OSError):
                p.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def log_call(
        self,
        tool_name: str,
        args: dict,
        result: str,
        elapsed_s: float,
        *,
        error: bool = False,
    ) -> None:
        """Emit a structured audit log entry with chained integrity hash."""
        try:
            with self._lock:
                self.setup()
                if self._last_chain_hash is None and self._path is not None:
                    self._last_chain_hash = _get_last_hash(self._path)
                prev_hash = self._last_chain_hash or "genesis"

                entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "tool": tool_name,
                    "args": _sanitize_audit_args(tool_name, args),
                    "result_len": len(result),
                    "result_sha256": hashlib.sha256(result.encode("utf-8")).hexdigest(),
                    "result_preview": _sanitize_audit_result(tool_name, result),
                    "elapsed_s": round(elapsed_s, 4),
                    "error": error,
                    "prev_hash": prev_hash,
                }
                chain_input = f"{prev_hash}:{json.dumps(entry, sort_keys=True, default=str)}"
                entry["chain_hash"] = hashlib.sha256(chain_input.encode()).hexdigest()

                self._logger.info(json.dumps(entry, separators=(",", ":")))
                self._last_chain_hash = str(entry["chain_hash"])
        except Exception as e:
            logging.getLogger(__name__).warning("audit logging unavailable: %s", e)

    def reset(self) -> None:
        """Reset all mutable state — used for test isolation."""
        if self._handler is not None:
            self._logger.removeHandler(self._handler)
            self._handler.close()
        self._handler = None
        self._path = None
        self._last_chain_hash = None

    def verify_chain(self, path: Path | None = None) -> tuple[bool, list[str]]:
        """Verify the integrity of the audit chain."""
        target = path or Path(".audit/tool-calls.jsonl")
        if not target.exists():
            return (True, [f"audit log not found at {target}"])

        issues: list[str] = []
        prev_hash = "genesis"

        with target.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    issues.append(f"line {lineno}: invalid JSON — {e}")
                    prev_hash = "genesis"
                    continue

                if "chain_hash" not in entry or "prev_hash" not in entry:
                    continue

                if entry["prev_hash"] != prev_hash:
                    issues.append(
                        f"line {lineno}: prev_hash mismatch — "
                        f"expected {prev_hash!r}, got {entry['prev_hash']!r}"
                    )

                stored_hash = entry.pop("chain_hash")
                chain_input = (
                    f"{entry['prev_hash']}:{json.dumps(entry, sort_keys=True, default=str)}"
                )
                computed = hashlib.sha256(chain_input.encode()).hexdigest()
                entry["chain_hash"] = stored_hash

                if stored_hash != computed:
                    issues.append(
                        f"line {lineno}: chain_hash mismatch — entry may have been tampered with"
                    )

                prev_hash = stored_hash

        return (len(issues) == 0, issues)


_default_auditor = AuditLogger()


def _get_last_hash(path: Path) -> str:
    """Read the chain_hash from the last line of the audit log."""
    if not path.exists():
        return "genesis"
    try:
        last_line = ""
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
        if last_line:
            return str(json.loads(last_line).get("chain_hash", "genesis"))
    except (json.JSONDecodeError, OSError):
        pass
    return "genesis"


def _sanitize_audit_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in args.items():
        if not isinstance(value, str):
            sanitized[key] = value
            continue
        lowered = key.lower()
        if any(marker in lowered for marker in _SENSITIVE_ARG_MARKERS):
            sanitized[key] = "[redacted]"
        elif tool_name == "write_file" and key == "content":
            sanitized[key] = f"[redacted content ({len(value)} chars)]"
        elif tool_name == "shell_exec" and key == "command":
            sanitized[key] = "[redacted shell command]"
        elif len(value) > 200:
            sanitized[key] = value[:200] + "..."
        else:
            sanitized[key] = value
    return sanitized


def _sanitize_audit_result(tool_name: str, result: str) -> str:
    if tool_name in _REDACTED_OUTPUT_TOOLS:
        return "[redacted]"
    return result[:500] + "..." if len(result) > 500 else result


# --- Module-level convenience functions delegating to the singleton ---


def setup_audit_log(path: str | Path = ".audit/tool-calls.jsonl") -> None:
    """Configure the audit logger to write JSON lines to a file."""
    _default_auditor.setup(path)


def verify_audit_chain(path: Path | None = None) -> tuple[bool, list[str]]:
    """Verify the integrity of the audit chain."""
    return _default_auditor.verify_chain(path)


def _audit_tool_call(
    tool_name: str,
    args: dict,
    result: str,
    elapsed_s: float,
    *,
    error: bool = False,
) -> None:
    _default_auditor.log_call(tool_name, args, result, elapsed_s, error=error)
