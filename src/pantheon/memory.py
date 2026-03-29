"""File-backed session persistence with window trimming and summary compression."""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ._types import Message

_log = logging.getLogger(__name__)
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class Store(Protocol):
    """Interface for conversation persistence."""

    def save(self, session_id: str, messages: list[Message]) -> None: ...
    def load(self, session_id: str) -> list[Message]: ...
    def list_sessions(self) -> list[SessionInfo]: ...


@dataclass
class SessionInfo:
    id: str
    agent: str = ""
    messages: int = 0
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    tier: str = ""


@dataclass
class _Session:
    id: str
    agent: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    tier: str = ""


class FileStore:
    """Persists sessions as JSON files in a directory."""

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _validate_session_id(self, session_id: str) -> None:
        if not _SAFE_SESSION_ID.fullmatch(session_id):
            raise ValueError(
                "session_id may only contain letters, numbers, underscores, and hyphens"
            )

    def _path(self, session_id: str) -> Path:
        self._validate_session_id(session_id)
        return self.dir / f"{session_id}.json"

    def save(
        self,
        session_id: str,
        messages: list[Message],
        agent: str = "",
        tags: list[str] | None = None,
        tier: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        path = self._path(session_id)

        existing = self._load_raw(session_id)
        created = existing.created_at if existing else now
        prev_tags = existing.tags if existing else []
        merged_tags = sorted(set(prev_tags + (tags or [])))

        sess = _Session(
            id=session_id,
            agent=agent or (existing.agent if existing else ""),
            messages=[m.to_dict() for m in messages],
            created_at=created,
            updated_at=now,
            tags=merged_tags,
            tier=tier or (existing.tier if existing else ""),
        )
        path.write_text(json.dumps(asdict(sess), indent=2), encoding="utf-8")
        try:
            if platform.system() != "Windows":
                path.chmod(0o600)
        except OSError:
            pass

    def load(self, session_id: str) -> list[Message]:
        self._validate_session_id(session_id)
        sess = self._load_raw(session_id)
        if not sess:
            return []
        return [
            Message(
                role=m.get("role", ""),
                content=m.get("content") or "",
                tool_calls=m.get("tool_calls", []),
                tool_call_id=m.get("tool_call_id", ""),
                name=m.get("name", ""),
            )
            for m in sess.messages
        ]

    def _load_raw(self, session_id: str) -> _Session | None:
        try:
            path = self._path(session_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _Session(
                **{k: v for k, v in data.items() if k in _Session.__dataclass_fields__}
            )
        except (json.JSONDecodeError, TypeError):
            return None

    def list_sessions(self) -> list[SessionInfo]:
        infos = []
        for p in sorted(self.dir.glob("*.json")):
            sess = self._load_raw(p.stem)
            if sess:
                infos.append(
                    SessionInfo(
                        id=sess.id,
                        agent=sess.agent,
                        messages=len(sess.messages),
                        updated_at=sess.updated_at,
                        tags=sess.tags,
                        tier=sess.tier,
                    )
                )
        return infos

    def search(self, keyword: str, agent: str = "", tier: str = "") -> list[SessionInfo]:
        """Search sessions by keyword in message content, optionally filtered by agent/tier."""
        keyword_lower = keyword.lower()
        results = []
        for p in sorted(self.dir.glob("*.json")):
            sess = self._load_raw(p.stem)
            if not sess:
                continue
            if agent and sess.agent != agent:
                continue
            if tier and sess.tier != tier:
                continue
            for m in sess.messages:
                content = m.get("content", "")
                if content and keyword_lower in content.lower():
                    results.append(
                        SessionInfo(
                            id=sess.id,
                            agent=sess.agent,
                            messages=len(sess.messages),
                            updated_at=sess.updated_at,
                            tags=sess.tags,
                            tier=sess.tier,
                        )
                    )
                    break
        return results


TIER_ORCHESTRATOR = "orchestrator"
TIER_AGENT = "agent"
TIER_SHARED = "shared"


def session_id(agent_name: str, label: str) -> str:
    """Generate a deterministic session ID."""
    h = hashlib.sha256(f"{agent_name}:{label}".encode()).hexdigest()
    return h[:16]


class WindowTrimmer:
    """Keeps only the last N message pairs plus the system prompt."""

    def __init__(self, max_pairs: int) -> None:
        self.max_pairs = max_pairs

    def trim(self, messages: list[Message]) -> list[Message]:
        conv_start = next((i for i, m in enumerate(messages) if m.role == "user"), len(messages))

        prefix = messages[:conv_start]
        conv = messages[conv_start:]

        max_msgs = self.max_pairs * 2
        if len(conv) <= max_msgs:
            return messages

        return prefix + conv[-max_msgs:]


class SummaryCompressor:
    """Compresses older conversation turns into a summary when threshold is exceeded."""

    def __init__(
        self,
        threshold_pairs: int,
        keep_pairs: int,
        summarize: Callable[[list[Message]], str],
    ) -> None:
        self.threshold_pairs = threshold_pairs
        self.keep_pairs = keep_pairs
        self.summarize = summarize

    def compress(self, messages: list[Message]) -> list[Message]:
        conv_start = next((i for i, m in enumerate(messages) if m.role == "user"), len(messages))

        prefix = messages[:conv_start]
        conv = messages[conv_start:]

        if len(conv) // 2 <= self.threshold_pairs:
            return messages

        keep_msgs = self.keep_pairs * 2
        to_summarize = conv[:-keep_msgs]
        to_keep = conv[-keep_msgs:]

        try:
            summary = self.summarize(to_summarize)
        except Exception:
            _log.warning("summary compression failed", exc_info=True)
            return messages

        return (
            prefix
            + [Message(role="system", content=f"[Conversation summary: {summary}]")]
            + to_keep
        )
