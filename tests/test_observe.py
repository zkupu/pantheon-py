"""Tests for observability — tracing, cost estimation, event handling."""

import pytest

from pantheon.agent import Event
from pantheon.gateway import Usage
from pantheon.observe import (
    ActivationTracker,
    Span,
    Tracker,
    classify_tool_event,
    cost_estimate,
)


class TestTracker:
    def test_start_creates_trace(self):
        t = Tracker()
        t.start("trace-1", "athena")
        assert "trace-1" in t._traces
        assert t._traces["trace-1"].agent == "athena"
        assert t._traces["trace-1"].started_at != ""

    def test_add_span(self):
        t = Tracker()
        t.start("t1", "kali")
        t.add_span("t1", Span(kind="tool_call", agent="kali", tool="read_file"))
        assert len(t._traces["t1"].spans) == 1
        assert t._traces["t1"].spans[0].tool == "read_file"
        assert t._traces["t1"].spans[0].timestamp != ""

    def test_add_span_to_nonexistent_trace(self):
        t = Tracker()
        t.add_span("nope", Span(kind="test"))

    def test_finish_returns_trace(self):
        t = Tracker()
        t.start("t1", "pele")
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        trace = t.finish("t1", usage)
        assert trace is not None
        assert trace.total_usage.total_tokens == 150
        assert trace.duration_ms >= 0

    def test_finish_nonexistent_returns_none(self):
        t = Tracker()
        assert t.finish("nope", Usage()) is None

    def test_event_handler(self):
        t = Tracker()
        t.start("t1", "test")
        handler = t.event_handler("t1")

        handler(Event(kind="tool_call", agent="test", tool="echo", content="data"))
        handler(Event(kind="reply", agent="test", content="done"))

        assert len(t._traces["t1"].spans) == 2
        assert t._traces["t1"].spans[0].kind == "tool_call"
        assert t._traces["t1"].spans[1].kind == "reply"

    def test_event_handler_truncates_long_content(self):
        t = Tracker()
        t.start("t1", "test")
        handler = t.event_handler("t1")

        handler(Event(kind="reply", agent="test", content="x" * 600))
        assert len(t._traces["t1"].spans[0].content) < 600
        assert t._traces["t1"].spans[0].content.endswith("...")


class TestActivationTracker:
    def test_compliant_turn(self):
        """Activation before work = compliant."""
        t = ActivationTracker()
        t.new_turn()
        t.record_activation("nuwa")
        t.record_work()
        assert t.compliance_rate == 1.0
        assert t.violations == []

    def test_violation_detected(self):
        """Work before activation = violation."""
        t = ActivationTracker()
        t.new_turn()
        t.record_work()
        assert t.compliance_rate == 0.0
        assert t.violations == [1]

    def test_multi_turn_compliance(self):
        """Mixed compliance across turns."""
        t = ActivationTracker()
        t.new_turn()
        t.record_activation("nuwa")
        t.record_work()
        t.new_turn()
        t.record_work()  # violation
        assert t.compliance_rate == 0.5
        assert t.violations == [2]

    def test_no_turns_is_fully_compliant(self):
        """Zero turns = 100% compliant (no opportunity to violate)."""
        t = ActivationTracker()
        assert t.compliance_rate == 1.0

    def test_multiple_activations_per_turn(self):
        """Multiple SKILL.md reads in one turn is valid."""
        t = ActivationTracker()
        t.new_turn()
        t.record_activation("nuwa")
        t.record_activation("themis")
        t.record_work()
        t.record_work()
        assert t.compliance_rate == 1.0

    def test_work_only_turn_then_compliant_turn(self):
        """First turn violates, second complies."""
        t = ActivationTracker()
        t.new_turn()
        t.record_work()
        t.new_turn()
        t.record_activation("kali")
        t.record_work()
        assert t.compliance_rate == 0.5

    def test_summary_structure(self):
        """Summary dict has expected keys."""
        t = ActivationTracker()
        t.new_turn()
        t.record_activation("nuwa")
        t.record_work()
        s = t.summary
        assert "turns" in s
        assert "violations" in s
        assert "compliance_rate" in s
        assert "violation_turns" in s
        assert s["turns"] == 1
        assert s["violations"] == 0

    def test_new_turn_resets_state(self):
        """new_turn clears per-turn state but preserves history."""
        t = ActivationTracker()
        t.new_turn()
        t.record_activation("nuwa")
        t.record_work()
        t.new_turn()
        assert t._turn_activations == []
        assert t._turn_has_work is False
        assert t._turn_count == 2


class TestClassifyToolEvent:
    def test_skill_read_is_activation(self):
        t = ActivationTracker()
        t.new_turn()
        classify_tool_event("read_file", {"path": ".agents/skills/nuwa/SKILL.md"}, t)
        assert t._turn_activations == ["nuwa"]

    def test_regular_read_is_work(self):
        t = ActivationTracker()
        t.new_turn()
        classify_tool_event("read_file", {"path": "src/pantheon/agent.py"}, t)
        assert t._turn_has_work is True
        assert t._turn_activations == []

    def test_shell_exec_is_work(self):
        t = ActivationTracker()
        t.new_turn()
        classify_tool_event("shell_exec", {"command": "echo hello"}, t)
        assert t._turn_has_work is True

    def test_backslash_paths_normalized(self):
        t = ActivationTracker()
        t.new_turn()
        classify_tool_event(
            "read_file",
            {"path": ".agents\\skills\\kali\\SKILL.md"},
            t,
        )
        assert t._turn_activations == ["kali"]


class TestCostEstimate:
    def test_opus_pricing(self):
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        cost = cost_estimate("bedrock-claude-opus-4-6", usage)
        expected = (1000 * 15.0 + 500 * 75.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_codex_pricing(self):
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        cost = cost_estimate("codex-mini", usage)
        expected = (1000 * 6.0 + 500 * 24.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_nano_pricing(self):
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        cost = cost_estimate("nano-lite", usage)
        expected = (1000 * 0.10 + 500 * 0.40) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_default_pricing(self):
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        cost = cost_estimate("some-unknown-model", usage)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_zero_usage(self):
        assert cost_estimate("opus", Usage()) == 0.0

    def test_custom_pricing(self):
        custom = {"mymodel": (1.0, 2.0)}
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        cost = cost_estimate("mymodel-v2", usage, pricing=custom)
        expected = (1000 * 1.0 + 500 * 2.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_custom_pricing_fallback(self):
        custom = {"mymodel": (1.0, 2.0)}
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        cost = cost_estimate("unknown", usage, pricing=custom)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)
