"""Shared types used across the Pantheon package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """Chat message with role, content, and optional tool call metadata."""

    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role}
        if self.content or not self.tool_calls:
            d["content"] = self.content
        else:
            d["content"] = None
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class Usage:
    """Token usage counters for a single LLM request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResponse:
    """LLM response containing content, tool calls, and token usage."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = ""


@dataclass
class Event:
    """Agent lifecycle event emitted during a ReAct loop iteration."""

    kind: str
    agent: str = ""
    tool: str = ""
    content: str = ""
    usage: Usage | None = None


class PantheonError(RuntimeError):
    """Base error for all Pantheon runtime failures."""


class BudgetExceededError(PantheonError):
    """Raised when an agent exceeds its configured budget."""


class DeadlineExceededError(PantheonError):
    """Raised when an operation exceeds its wall-clock deadline."""


class DelegationDepthError(PantheonError):
    """Raised when agent-as-tool delegation exceeds the depth limit."""


class CancelledError(PantheonError):
    """Raised when an agent is cancelled via cancel()."""


_CHARS_PER_TOKEN = 4


def estimate_tokens(messages: list[Message]) -> int:
    """Rough token estimate: ~4 chars per token across all message content."""
    return sum(len(m.content) for m in messages) // _CHARS_PER_TOKEN
