"""Tests for budget tracking and enforcement."""

import pytest

from pantheon.observe import Budget, BudgetStatus, BudgetTracker


class TestBudget:
    def test_defaults(self):
        b = Budget()
        assert b.max_usd == 0.0
        assert b.max_tokens == 0
        assert b.max_tool_calls == 0

    def test_is_set_false(self):
        assert not Budget().is_set()

    def test_is_set_usd(self):
        assert Budget(max_usd=1.0).is_set()

    def test_is_set_tokens(self):
        assert Budget(max_tokens=1000).is_set()

    def test_is_set_tool_calls(self):
        assert Budget(max_tool_calls=5).is_set()


class TestBudgetStatus:
    def test_not_exceeded_when_empty(self):
        s = BudgetStatus()
        assert not s.exceeded

    def test_usd_exceeded(self):
        s = BudgetStatus(spent_usd=2.0, budget=Budget(max_usd=1.0))
        assert s.exceeded

    def test_usd_not_exceeded(self):
        s = BudgetStatus(spent_usd=0.5, budget=Budget(max_usd=1.0))
        assert not s.exceeded

    def test_tokens_exceeded(self):
        s = BudgetStatus(tokens_used=1500, budget=Budget(max_tokens=1000))
        assert s.exceeded

    def test_tokens_equal_limit_not_exceeded(self):
        s = BudgetStatus(tokens_used=1000, budget=Budget(max_tokens=1000))
        assert not s.exceeded

    def test_tokens_not_exceeded(self):
        s = BudgetStatus(tokens_used=500, budget=Budget(max_tokens=1000))
        assert not s.exceeded

    def test_tool_calls_exceeded(self):
        s = BudgetStatus(tool_calls_used=10, budget=Budget(max_tool_calls=5))
        assert s.exceeded

    def test_tool_calls_equal_limit_not_exceeded(self):
        s = BudgetStatus(tool_calls_used=5, budget=Budget(max_tool_calls=5))
        assert not s.exceeded

    def test_usd_remaining_infinite_when_no_limit(self):
        s = BudgetStatus()
        assert s.usd_remaining == float("inf")

    def test_usd_remaining_calculated(self):
        s = BudgetStatus(spent_usd=0.3, budget=Budget(max_usd=1.0))
        assert s.usd_remaining == pytest.approx(0.7)

    def test_tokens_remaining_large_when_no_limit(self):
        s = BudgetStatus()
        assert s.tokens_remaining == 2**31

    def test_tokens_remaining_calculated(self):
        s = BudgetStatus(tokens_used=400, budget=Budget(max_tokens=1000))
        assert s.tokens_remaining == 600

    def test_remaining_floors_at_zero(self):
        s = BudgetStatus(spent_usd=5.0, budget=Budget(max_usd=1.0))
        assert s.usd_remaining == 0.0


class TestBudgetTracker:
    def test_initial_status(self):
        bt = BudgetTracker(Budget(max_usd=1.0))
        assert bt.status.spent_usd == 0.0
        assert not bt.status.exceeded

    def test_record_accumulates(self):
        bt = BudgetTracker()
        bt.record(0.1, 100, 1)
        bt.record(0.2, 200, 2)
        s = bt.status
        assert s.spent_usd == pytest.approx(0.3)
        assert s.tokens_used == 300
        assert s.tool_calls_used == 3

    def test_record_returns_exceeded_status(self):
        bt = BudgetTracker(Budget(max_usd=0.5))
        s1 = bt.record(0.3, 100)
        assert not s1.exceeded
        s2 = bt.record(0.3, 100)
        assert s2.exceeded

    def test_no_budget_never_exceeded(self):
        bt = BudgetTracker()
        bt.record(100.0, 1_000_000, 999)
        assert not bt.status.exceeded

    def test_token_limit_triggers(self):
        bt = BudgetTracker(Budget(max_tokens=500))
        bt.record(0, 300)
        assert not bt.status.exceeded
        bt.record(0, 300)
        assert bt.status.exceeded

    def test_tool_call_limit_triggers(self):
        bt = BudgetTracker(Budget(max_tool_calls=3))
        bt.record(0, 0, 2)
        assert not bt.status.exceeded
        bt.record(0, 0, 2)
        assert bt.status.exceeded
