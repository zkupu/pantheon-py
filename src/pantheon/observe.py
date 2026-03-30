"""Structured logging, tracing, cost estimation, and budget awareness."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from ._types import Event, Usage

_log = logging.getLogger(__name__)

_SKILL_PATH_PATTERN = re.compile(r"\.agents/skills/([^/]+)/SKILL\.md")


@dataclass
class Span:
    kind: str
    agent: str = ""
    tool: str = ""
    content: str = ""
    timestamp: str = ""


@dataclass
class Trace:
    id: str
    agent: str
    started_at: str = ""
    spans: list[Span] = field(default_factory=list)
    total_usage: Usage = field(default_factory=Usage)
    duration_ms: float = 0.0
    tool_call_count: int = 0
    estimated_cost_usd: float = 0.0


class Tracker:
    """Collects traces across multiple agent invocations."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._traces: dict[str, Trace] = {}
        self._starts: dict[str, float] = {}

    def start(self, trace_id: str, agent_name: str) -> None:
        with self._lock:
            self._traces[trace_id] = Trace(
                id=trace_id,
                agent=agent_name,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._starts[trace_id] = time.monotonic()

    def add_span(self, trace_id: str, span: Span) -> None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace:
                span.timestamp = datetime.now(timezone.utc).isoformat()
                trace.spans.append(span)
                if span.kind == "tool_call":
                    trace.tool_call_count += 1

    def finish(self, trace_id: str, usage: Usage, model: str = "") -> Trace | None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return None
            trace.total_usage = usage
            start = self._starts.get(trace_id, time.monotonic())
            trace.duration_ms = (time.monotonic() - start) * 1000
            trace.estimated_cost_usd = cost_estimate(model, usage)
            return trace

    def event_handler(self, trace_id: str) -> Callable[[Event], None]:
        def handler(e: Event) -> None:
            content = e.content[:500] + "..." if len(e.content) > 500 else e.content
            self.add_span(trace_id, Span(kind=e.kind, agent=e.agent, tool=e.tool, content=content))

        return handler


# --- Cost estimation with 2026 pricing ---

_DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.25, 1.25),
    "codex": (6.0, 24.0),
    "nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5": (10.0, 40.0),
    "gemini-2": (1.25, 5.0),
    "gemini-3": (0.50, 2.0),
}
_FALLBACK_RATE: tuple[float, float] = (3.0, 15.0)


def cost_estimate(
    model: str,
    usage: Usage,
    pricing: dict[str, tuple[float, float]] | None = None,
) -> float:
    """Rough USD cost estimate for a model and token usage.

    The pricing dict maps model name substrings to (input_rate, output_rate)
    per million tokens. Falls back to a default rate if no key matches.
    Note: output tokens typically cost 3-5x more than input tokens.
    """
    rates = pricing if pricing is not None else _DEFAULT_PRICING
    in_rate, out_rate = _FALLBACK_RATE
    for key, (ir, orr) in rates.items():
        if key in model:
            in_rate, out_rate = ir, orr
            break
    cost = usage.prompt_tokens * in_rate + usage.completion_tokens * out_rate
    return cost / 1_000_000


# --- Activation compliance tracking ---


@dataclass
class ActivationTracker:
    """Tracks whether the activation rule is followed per turn.

    The activation rule requires that SKILL.md reads precede any project
    file reads, shell commands, or code writes within a turn.  This tracker
    records activation and work events and flags violations.
    """

    _turn_activations: list[str] = field(default_factory=list)
    _turn_has_work: bool = False
    _violations: list[int] = field(default_factory=list)
    _turn_count: int = 0
    _tool_calls_this_turn: int = 0
    _decay_warning_injected: bool = False

    def record_activation(self, skill_name: str) -> None:
        """Record a SKILL.md read."""
        self._turn_activations.append(skill_name)

    def record_work(self) -> None:
        """Record a project file read, shell command, or code write."""
        if not self._turn_activations and not self._turn_has_work:
            self._violations.append(self._turn_count)
        self._turn_has_work = True

    def record_tool_calls(self, count: int) -> None:
        """Record tool calls executed within the current turn."""
        self._tool_calls_this_turn += count

    def needs_self_audit(self) -> bool:
        """True when the current turn has hit a 5-call audit boundary."""
        return self._tool_calls_this_turn > 0 and self._tool_calls_this_turn % 5 == 0

    def needs_decay_warning(self) -> bool:
        """True once when the conversation reaches 5+ turns."""
        return self._turn_count >= 5 and not self._decay_warning_injected

    def mark_decay_warning_injected(self) -> None:
        self._decay_warning_injected = True

    def new_turn(self) -> None:
        """Start a new turn (user message received)."""
        self._turn_count += 1
        self._turn_activations.clear()
        self._turn_has_work = False
        self._tool_calls_this_turn = 0

    @property
    def compliance_rate(self) -> float:
        if self._turn_count == 0:
            return 1.0
        return 1.0 - (len(self._violations) / self._turn_count)

    @property
    def violations(self) -> list[int]:
        return list(self._violations)

    @property
    def summary(self) -> dict[str, object]:
        return {
            "turns": self._turn_count,
            "violations": len(self._violations),
            "compliance_rate": self.compliance_rate,
            "violation_turns": list(self._violations),
        }


def classify_tool_event(
    tool_name: str,
    args: dict[str, object],
    tracker: ActivationTracker,
) -> None:
    """Route a tool call event to the activation tracker."""
    if tool_name == "read_file":
        path = str(args.get("path", ""))
        match = _SKILL_PATH_PATTERN.search(path.replace("\\", "/"))
        if match:
            tracker.record_activation(match.group(1))
            return
    tracker.record_work()


# --- Budget awareness ---


@dataclass
class Budget:
    """Per-session or per-agent spending limit."""

    max_usd: float = 0.0
    max_tokens: int = 0
    max_tool_calls: int = 0

    def is_set(self) -> bool:
        return self.max_usd > 0 or self.max_tokens > 0 or self.max_tool_calls > 0


@dataclass
class BudgetStatus:
    spent_usd: float = 0.0
    tokens_used: int = 0
    tool_calls_used: int = 0
    budget: Budget = field(default_factory=Budget)

    @property
    def usd_remaining(self) -> float:
        if self.budget.max_usd <= 0:
            return float("inf")
        return max(0.0, self.budget.max_usd - self.spent_usd)

    @property
    def tokens_remaining(self) -> int:
        if self.budget.max_tokens <= 0:
            return 2**31
        return max(0, self.budget.max_tokens - self.tokens_used)

    @property
    def exceeded(self) -> bool:
        return (
            (self.budget.max_usd > 0 and self.spent_usd > self.budget.max_usd)
            or (self.budget.max_tokens > 0 and self.tokens_used > self.budget.max_tokens)
            or (
                self.budget.max_tool_calls > 0
                and self.tool_calls_used > self.budget.max_tool_calls
            )
        )


class BudgetTracker:
    """Tracks cumulative spend and usage against optional limits."""

    def __init__(self, budget: Budget | None = None) -> None:
        self._lock = Lock()
        self._budget = budget or Budget()
        self._spent_usd = 0.0
        self._tokens_used = 0
        self._tool_calls = 0

    def record(self, cost_usd: float, tokens: int, tool_calls: int = 0) -> BudgetStatus:
        with self._lock:
            self._spent_usd += cost_usd
            self._tokens_used += tokens
            self._tool_calls += tool_calls
            status = self.status
        if status.exceeded:
            _log.warning(
                "budget exceeded: $%.4f / $%.4f, %d / %d tokens, %d / %d tool calls",
                self._spent_usd,
                self._budget.max_usd,
                self._tokens_used,
                self._budget.max_tokens,
                self._tool_calls,
                self._budget.max_tool_calls,
            )
        return status

    @property
    def status(self) -> BudgetStatus:
        return BudgetStatus(
            spent_usd=self._spent_usd,
            tokens_used=self._tokens_used,
            tool_calls_used=self._tool_calls,
            budget=self._budget,
        )
