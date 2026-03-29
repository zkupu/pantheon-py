"""Agent runtime — load from skills, ReAct loop, streaming."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ._types import (
    BudgetExceededError,
    CancelledError,
    ChatResponse,
    DeadlineExceededError,
    DelegationDepthError,  # noqa: F401 — re-exported for backward compat
    Event,
    Message,
    PantheonError,
    Usage,
    estimate_tokens,
)
from .gateway import Client
from .skill import Skill, discover_map
from .tools import Registry, builtins

if TYPE_CHECKING:
    from .observe import ActivationTracker, Budget, BudgetStatus, BudgetTracker

_log = logging.getLogger(__name__)

_DEFAULT_CONTEXT_LIMIT = 128_000
_COMPACTION_THRESHOLD = 0.75

_estimate_tokens = estimate_tokens


class Agent:
    """Agentic runtime that executes a ReAct loop with tool use.

    Loads configuration from a Skill, connects to an LLM via Client,
    and iteratively reasons + acts until a final answer or budget exhaustion.
    """

    def __init__(
        self,
        skill: Skill,
        client: Client,
        context_limit: int = _DEFAULT_CONTEXT_LIMIT,
        budget: Budget | None = None,
        deadline_s: float = 0.0,
    ) -> None:
        """Initialize an agent from a skill definition and LLM client.

        Args:
            skill: Parsed SKILL.md with persona, model, and tool configuration.
            client: LLM gateway client for chat completions.
            context_limit: Max tokens before context compaction triggers.
            budget: Optional spending limits for tokens, cost, and tool calls.
            deadline_s: Wall-clock timeout in seconds (0 = no deadline).
        """
        from .observe import ActivationTracker as _AT
        from .observe import BudgetTracker as _BT

        self.skill = skill
        self.client = client
        self.tools = Registry()
        self.on_event: Callable[[Event], None] | None = None
        self.system_suffix: str = ""
        self.context_limit = context_limit
        self.deadline_s = deadline_s
        self._budget_tracker: BudgetTracker | None = (
            _BT(budget) if budget and budget.is_set() else None
        )
        self._activation_tracker: ActivationTracker = _AT()
        self._compactor: Callable[[list[Message]], list[Message]] | None = None
        self._cancel = threading.Event()
        self._history: list[Message] = []
        self.reset()

    @property
    def name(self) -> str:
        return self.skill.name

    @property
    def history(self) -> list[Message]:
        return self._history

    @property
    def persona(self) -> str:
        return self.skill.persona

    @property
    def model(self) -> str:
        return self.skill.model

    @property
    def use_for(self) -> str:
        return self.skill.description

    @property
    def context_tokens(self) -> int:
        """Estimated tokens currently in the conversation history."""
        return _estimate_tokens(self._history)

    @property
    def context_utilization(self) -> float:
        """Fraction of context window used (0.0 to 1.0+)."""
        if self.context_limit <= 0:
            return 0.0
        return self.context_tokens / self.context_limit

    def set_compactor(
        self,
        compactor: Callable[[list[Message]], list[Message]],
    ) -> None:
        """Set a function to compact history when context budget is tight.

        The compactor receives the full history and returns a compacted version.
        Compatible with WindowTrimmer.trim and SummaryCompressor.compress.
        """
        self._compactor = compactor

    def _maybe_compact(self) -> None:
        """Trigger compaction if context utilization exceeds threshold."""
        if self._compactor is not None and self.context_utilization > _COMPACTION_THRESHOLD:
            before = self.context_tokens
            self._history = self._compactor(self._history)
            after = self.context_tokens
            _log.info(
                "agent '%s': compacted context %d -> %d tokens (%.0f%% -> %.0f%%)",
                self.name,
                before,
                after,
                before / self.context_limit * 100,
                after / self.context_limit * 100,
            )

    def emit(self, kind: str, **kw: Any) -> None:
        if self.on_event:
            self.on_event(Event(kind=kind, agent=self.name, **kw))

    def reset(self) -> None:
        body = self.skill.body
        if self.system_suffix:
            body += self.system_suffix
        self._history = [Message(role="system", content=body)]

    def load_history(self, messages: list[Message]) -> None:
        """Replace the current conversation history with persisted messages."""
        self._history = list(messages) if messages else []
        if not self._history:
            self.reset()

    def _budget_error(
        self,
        iteration: int,
        phase: str,
        status: BudgetStatus,
    ) -> BudgetExceededError:
        return BudgetExceededError(
            f"agent '{self.name}' {phase} at iteration {iteration}: "
            f"${status.spent_usd:.4f} spent, "
            f"{status.tokens_used} tokens, "
            f"{status.tool_calls_used} tool calls"
        )

    def _request_max_tokens(self, iteration: int) -> int:
        max_tokens = self.skill.max_tokens
        if not self._budget_tracker:
            return max_tokens

        status = self._budget_tracker.status
        if status.exceeded or (status.budget.max_usd > 0 and status.usd_remaining <= 0):
            raise self._budget_error(iteration, "exhausted budget before request", status)

        if status.budget.max_tokens > 0:
            estimated_prompt_tokens = max(_estimate_tokens(self._history), 1)
            available_completion = status.tokens_remaining - estimated_prompt_tokens
            if available_completion <= 0:
                raise BudgetExceededError(
                    f"agent '{self.name}' lacks token budget for iteration {iteration}: "
                    f"{status.tokens_used} tokens used, "
                    f"{estimated_prompt_tokens} estimated prompt tokens pending, "
                    f"limit {status.budget.max_tokens}"
                )
            max_tokens = min(max_tokens, available_completion)

        return max_tokens

    def _record_response_usage(self, resp: ChatResponse, iteration: int) -> None:
        if not self._budget_tracker:
            return

        from .observe import cost_estimate as _cost_est

        status_before = self._budget_tracker.status
        iter_cost = _cost_est(self.model, resp.usage)
        tool_count = len(resp.tool_calls) if resp.tool_calls else 0

        if resp.tool_calls and status_before.budget.max_tool_calls > 0:
            projected = status_before.tool_calls_used + tool_count
            if projected > status_before.budget.max_tool_calls:
                self._budget_tracker.record(iter_cost, resp.usage.total_tokens, 0)
                raise BudgetExceededError(
                    f"agent '{self.name}' tool batch at iteration {iteration} "
                    f"would exceed max_tool_calls: "
                    f"{projected} > {status_before.budget.max_tool_calls}"
                )

        status = self._budget_tracker.record(iter_cost, resp.usage.total_tokens, tool_count)
        if status.exceeded:
            phase = (
                "exceeded budget before tool execution"
                if resp.tool_calls
                else "exceeded budget after response"
            )
            raise self._budget_error(iteration, phase, status)

    def send(self, msg: str) -> str:
        self._history.append(Message(role="user", content=msg))
        max_tokens = self._request_max_tokens(0)
        resp = self.client.chat(
            model=self.model,
            messages=self._history,
            temperature=self.skill.temperature,
            max_tokens=max_tokens,
        )
        self._record_response_usage(resp, 0)
        self._history.append(Message(role="assistant", content=resp.content))
        return resp.content

    def send_stream(
        self,
        msg: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        self._history.append(Message(role="user", content=msg))
        max_tokens = self._request_max_tokens(0)
        resp = self.client.chat_stream_full(
            model=self.model,
            messages=self._history,
            temperature=self.skill.temperature,
            max_tokens=max_tokens,
            on_chunk=on_chunk,
        )
        self._record_response_usage(resp, 0)
        self._history.append(Message(role="assistant", content=resp.content))
        return resp.content

    def run(self, msg: str) -> str:
        """Full ReAct loop: reason → call tools → observe → repeat."""
        return self.run_stream(msg)

    def cancel(self) -> None:
        """Signal the agent to stop at the next ReAct iteration."""
        self._cancel.set()

    @property
    def activation_tracker(self) -> ActivationTracker:
        return self._activation_tracker

    def run_stream(
        self,
        msg: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """ReAct loop with optional streaming. Streams content deltas via on_chunk."""
        import time as _time

        self._cancel.clear()
        self._activation_tracker.new_turn()
        self._history.append(Message(role="user", content=msg))
        self._maybe_compact()

        tool_defs = self.tools.definitions() or None
        total = Usage()
        start = _time.monotonic()

        for i in range(self.skill.max_iterations):
            if self._cancel.is_set():
                raise CancelledError(f"agent '{self.name}' cancelled at iteration {i}")
            if self.deadline_s > 0:
                elapsed = _time.monotonic() - start
                if elapsed >= self.deadline_s:
                    raise DeadlineExceededError(
                        f"agent '{self.name}' exceeded deadline of "
                        f"{self.deadline_s}s at iteration {i} "
                        f"({elapsed:.1f}s elapsed)"
                    )
            max_tokens = self._request_max_tokens(i)

            if on_chunk is not None:
                resp = self.client.chat_stream_full(
                    model=self.model,
                    messages=self._history,
                    temperature=self.skill.temperature,
                    max_tokens=max_tokens,
                    tools=tool_defs,
                    on_chunk=on_chunk,
                )
            else:
                resp = self.client.chat(
                    model=self.model,
                    messages=self._history,
                    temperature=self.skill.temperature,
                    max_tokens=max_tokens,
                    tools=tool_defs,
                )

            total.prompt_tokens += resp.usage.prompt_tokens
            total.completion_tokens += resp.usage.completion_tokens
            total.total_tokens += resp.usage.total_tokens

            self._record_response_usage(resp, i)

            if resp.tool_calls:
                self._history.append(
                    Message(
                        role="assistant",
                        content=resp.content,
                        tool_calls=resp.tool_calls,
                    )
                )

                for tc in resp.tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    tool_args_raw = fn.get("arguments", "")
                    self.emit(
                        "tool_call",
                        tool=tool_name,
                        content=tool_args_raw,
                    )
                    try:
                        import json as _json

                        from .observe import classify_tool_event

                        parsed = _json.loads(tool_args_raw) if tool_args_raw else {}
                        classify_tool_event(tool_name, parsed, self._activation_tracker)
                    except Exception:
                        pass

                results = self.tools.execute_all(resp.tool_calls)
                for r in results:
                    self.emit("tool_result", content=r["content"])
                    self._history.append(
                        Message(
                            role="tool",
                            content=r["content"],
                            tool_call_id=r.get("tool_call_id", ""),
                        )
                    )
                self._maybe_compact()
                continue

            self._history.append(Message(role="assistant", content=resp.content))
            self.emit("reply", content=resp.content, usage=total)
            _log.debug(
                "agent '%s': activation compliance %.0f%% (%s)",
                self.name,
                self._activation_tracker.compliance_rate * 100,
                self._activation_tracker.summary,
            )
            return resp.content

        raise PantheonError(
            f"agent '{self.name}' hit max iterations"
            f" ({self.skill.max_iterations});"
            " increase max_iterations or simplify the task"
        )


def load_all(directory: str, client: Client) -> dict[str, Agent]:
    skills = discover_map(directory)
    return {name: Agent(s, client) for name, s in skills.items()}


def equip_tools(agent: Agent, registry: Registry | None = None) -> None:
    registry = registry or builtins()
    allowed = set(agent.skill.allowed_tool_names)
    tool_names = [name for name in agent.skill.tool_names if not allowed or name in allowed]
    blocked = [name for name in agent.skill.tool_names if allowed and name not in allowed]
    for name in blocked:
        _log.warning(
            "agent '%s': tool '%s' requested but not in allowed_tools",
            agent.name,
            name,
        )
    for name in tool_names:
        tool = registry.get(name)
        if tool:
            agent.tools.register(tool)
        else:
            _log.warning(
                "agent '%s': tool '%s' not found in registry",
                agent.name,
                name,
            )
