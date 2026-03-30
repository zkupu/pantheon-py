"""Tests for shared types — estimate_tokens and Message serialization."""

from __future__ import annotations

from pantheon._types import Message, estimate_tokens


class TestEstimateTokens:
    def test_empty_messages_returns_zero(self):
        assert estimate_tokens([]) == 0

    def test_single_message_divides_by_four(self):
        msg = Message(role="user", content="a" * 100)
        assert estimate_tokens([msg]) == 25

    def test_multiple_messages_sums_content(self):
        msgs = [
            Message(role="system", content="a" * 40),
            Message(role="user", content="b" * 60),
        ]
        assert estimate_tokens(msgs) == 25  # (40 + 60) // 4

    def test_empty_content_contributes_zero(self):
        msgs = [
            Message(role="assistant", content=""),
            Message(role="user", content="a" * 8),
        ]
        assert estimate_tokens(msgs) == 2

    def test_known_input_regression(self):
        """Known-value regression: 13 chars -> 3 tokens (floor division)."""
        msgs = [Message(role="user", content="Hello, world!")]
        assert estimate_tokens(msgs) == 3  # 13 // 4 = 3
