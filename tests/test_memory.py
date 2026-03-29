"""Tests for session persistence and memory utilities."""

import tempfile
from pathlib import Path

import pytest

from pantheon.gateway import Message
from pantheon.memory import FileStore, SummaryCompressor, WindowTrimmer, session_id


class TestFileStore:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(d)
            messages = [
                Message(role="system", content="You are helpful."),
                Message(role="user", content="Hello"),
                Message(
                    role="assistant",
                    content="",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {
                                "name": "test",
                                "arguments": '{"x":1}',
                            },
                        }
                    ],
                ),
                Message(role="tool", content="result", tool_call_id="tc-1"),
                Message(role="assistant", content="Done."),
            ]
            store.save("sess-1", messages)
            loaded = store.load("sess-1")

            assert len(loaded) == len(messages)
            for i, m in enumerate(loaded):
                assert m.role == messages[i].role
                assert m.content == messages[i].content

            assert len(loaded[2].tool_calls) == 1
            assert loaded[2].tool_calls[0]["id"] == "tc-1"
            assert loaded[3].tool_call_id == "tc-1"

    def test_load_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(d)
            result = store.load("nonexistent")
            assert result == []

    def test_list_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(d)
            store.save("a", [Message(role="user", content="hi")])
            store.save("b", [Message(role="user", content="hello")])
            infos = store.list_sessions()
            assert len(infos) == 2

    def test_search_filters_by_keyword_agent_and_tier(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(d)
            store.save(
                "match-a",
                [Message(role="user", content="hello pantheon")],
                agent="athena",
                tier="shared",
            )
            store.save(
                "match-b",
                [Message(role="user", content="hello world")],
                agent="kali",
                tier="agent",
            )

            results = store.search("pantheon", agent="athena", tier="shared")

            assert [item.id for item in results] == ["match-a"]

    def test_list_sessions_skips_corrupt_json(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(d)
            store.save("ok", [Message(role="user", content="hi")])
            Path(d, "broken.json").write_text("{not json", encoding="utf-8")

            infos = store.list_sessions()

            assert [item.id for item in infos] == ["ok"]

    def test_rejects_unsafe_session_id(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(d)

            with pytest.raises(ValueError, match="session_id"):
                store.save("../escape", [Message(role="user", content="hi")])

            with pytest.raises(ValueError, match="session_id"):
                store.load("../escape")


class TestWindowTrimmer:
    def test_trims_to_max_pairs(self):
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="u2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="u3"),
            Message(role="assistant", content="a3"),
        ]
        trimmer = WindowTrimmer(max_pairs=2)
        result = trimmer.trim(msgs)
        assert len(result) == 5  # system + 2 pairs
        assert result[0].role == "system"
        assert result[1].content == "u2"

    def test_no_trim_when_under_limit(self):
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
        ]
        trimmer = WindowTrimmer(max_pairs=5)
        result = trimmer.trim(msgs)
        assert len(result) == 3


class TestSummaryCompressor:
    def test_compresses_when_over_threshold(self):
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="u2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="u3"),
            Message(role="assistant", content="a3"),
        ]
        compressor = SummaryCompressor(
            threshold_pairs=2,
            keep_pairs=1,
            summarize=lambda msgs: "summary of older turns",
        )
        result = compressor.compress(msgs)
        assert any("[Conversation summary:" in m.content for m in result)
        assert result[-1].content == "a3"

    def test_no_compress_under_threshold(self):
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
        ]
        compressor = SummaryCompressor(
            threshold_pairs=5, keep_pairs=1, summarize=lambda msgs: "summary"
        )
        result = compressor.compress(msgs)
        assert len(result) == 3

    def test_returns_original_messages_when_summary_fails(self):
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="u2"),
            Message(role="assistant", content="a2"),
            Message(role="user", content="u3"),
            Message(role="assistant", content="a3"),
        ]
        compressor = SummaryCompressor(
            threshold_pairs=2,
            keep_pairs=1,
            summarize=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        assert compressor.compress(msgs) == msgs


class TestSessionId:
    def test_deterministic(self):
        assert session_id("agent", "label") == session_id("agent", "label")

    def test_different_inputs(self):
        assert session_id("agent", "a") != session_id("agent", "b")
