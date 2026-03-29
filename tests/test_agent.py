"""Tests for the agent runtime — ReAct loop, tool dispatch, lifecycle."""

from unittest.mock import MagicMock

import pytest

from pantheon.agent import (
    Agent,
    BudgetExceededError,
    CancelledError,
    DeadlineExceededError,
    Event,
    PantheonError,
    equip_tools,
    load_all,
)
from pantheon.gateway import ChatResponse, Client, Message, Usage
from pantheon.observe import Budget
from pantheon.tools import Registry, Tool, strict_schema
from tests.echo_tool import EchoTool


def _client_returning(*responses: ChatResponse) -> Client:
    client = MagicMock(spec=Client)
    client.chat = MagicMock(side_effect=list(responses))
    client.chat_stream = MagicMock(side_effect=[r.content for r in responses])
    client.chat_stream_full = MagicMock(side_effect=list(responses))
    return client


class _OtherTool(Tool):
    def name(self) -> str:
        return "other"

    def description(self) -> str:
        return "Other"

    def parameters(self) -> dict:
        return strict_schema({}, [])

    def execute(self, args: dict) -> str:
        return "ok"


class TestAgentProperties:
    def test_name_from_skill(self, tmp_skill):
        a = Agent(tmp_skill("athena"), _client_returning())
        assert a.name == "athena"

    def test_persona_from_skill(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        assert a.persona == "Test Persona"

    def test_model_from_skill(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        assert a.model == "test-model"

    def test_use_for_from_description(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        assert a.use_for == "test skill"


class TestAgentReset:
    def test_initializes_with_system_message(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        assert len(a.history) == 1
        assert a.history[0].role == "system"
        assert a.history[0].content == "You are test."

    def test_reset_clears_and_restores_system(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        a._history.append(Message(role="user", content="extra"))
        assert len(a.history) == 2
        a.reset()
        assert len(a.history) == 1
        assert a.history[0].role == "system"

    def test_system_suffix_appended(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        a.system_suffix = "\nExtra instructions."
        a.reset()
        assert a.history[0].content.endswith("\nExtra instructions.")


class TestAgentSend:
    def test_send_appends_messages(self, tmp_skill):
        resp = ChatResponse(content="reply", usage=Usage())
        client = _client_returning(resp)
        a = Agent(tmp_skill(), client)

        result = a.send("hello")
        assert result == "reply"
        assert len(a.history) == 3
        assert a.history[1].role == "user"
        assert a.history[2].role == "assistant"

    def test_send_stream_appends_messages(self, tmp_skill):
        resp = ChatResponse(content="streamed", usage=Usage(1, 1, 2))
        client = _client_returning(resp)
        client.chat_stream_full = MagicMock(return_value=resp)
        a = Agent(tmp_skill(), client)

        chunks: list[str] = []
        result = a.send_stream("hello", on_chunk=chunks.append)
        assert result == "streamed"
        assert a.history[-1].role == "assistant"


class TestAgentEmit:
    def test_emit_calls_handler(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        events: list[Event] = []
        a.on_event = events.append

        a.emit("test_event", content="data")
        assert len(events) == 1
        assert events[0].kind == "test_event"
        assert events[0].agent == "test"
        assert events[0].content == "data"

    def test_emit_no_handler_is_noop(self, tmp_skill):
        a = Agent(tmp_skill(), _client_returning())
        a.on_event = None
        a.emit("test_event")


class TestAgentReactLoop:
    def test_simple_reply_no_tools(self, tmp_skill):
        resp = ChatResponse(content="answer", usage=Usage(1, 2, 3))
        client = _client_returning(resp)
        a = Agent(tmp_skill(), client)

        result = a.run("question")
        assert result == "answer"

    def test_tool_call_then_reply(self, tmp_skill):
        tool_resp = ChatResponse(
            content="",
            usage=Usage(5, 5, 10),
            tool_calls=[
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg":"hello"}'},
                }
            ],
        )
        final_resp = ChatResponse(content="done", usage=Usage(10, 5, 15))
        client = _client_returning(tool_resp, final_resp)
        a = Agent(tmp_skill(tools=["echo"]), client)
        a.tools.register(EchoTool())

        result = a.run("test")
        assert result == "done"
        assert client.chat.call_count == 2

    def test_max_iterations_raises(self, tmp_skill):
        tool_resp = ChatResponse(
            content="",
            usage=Usage(),
            tool_calls=[
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg":"loop"}'},
                }
            ],
        )
        client = MagicMock(spec=Client)
        client.chat = MagicMock(return_value=tool_resp)

        s = tmp_skill(tools=["echo"])
        s.metadata.max_iterations = 3
        a = Agent(s, client)
        a.tools.register(EchoTool())

        with pytest.raises(RuntimeError, match="max iterations"):
            a.run("infinite loop")
        assert client.chat.call_count == 3

    def test_run_stream_with_on_chunk(self, tmp_skill):
        resp = ChatResponse(content="streamed", usage=Usage(1, 1, 2))
        client = _client_returning(resp)
        client.chat_stream_full = MagicMock(return_value=resp)
        a = Agent(tmp_skill(), client)

        chunks: list[str] = []
        result = a.run_stream("test", on_chunk=chunks.append)
        assert result == "streamed"
        client.chat_stream_full.assert_called_once()

    def test_emits_events_during_loop(self, tmp_skill):
        tool_resp = ChatResponse(
            content="",
            usage=Usage(),
            tool_calls=[
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg":"hi"}'},
                }
            ],
        )
        final_resp = ChatResponse(content="done", usage=Usage(5, 3, 8))
        client = _client_returning(tool_resp, final_resp)

        a = Agent(tmp_skill(tools=["echo"]), client)
        a.tools.register(EchoTool())

        events: list[Event] = []
        a.on_event = events.append
        a.run("test")

        kinds = [e.kind for e in events]
        assert "tool_call" in kinds
        assert "tool_result" in kinds
        assert "reply" in kinds

    def test_exact_tool_call_limit_allows_follow_up_response(self, tmp_skill):
        tool_resp = ChatResponse(
            content="",
            usage=Usage(5, 5, 10),
            tool_calls=[
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg":"hello"}'},
                }
            ],
        )
        final_resp = ChatResponse(content="done", usage=Usage(2, 2, 4))
        client = _client_returning(tool_resp, final_resp)
        a = Agent(tmp_skill(tools=["echo"]), client, budget=Budget(max_tool_calls=1))
        a.tools.register(EchoTool())

        assert a.run("test") == "done"

    def test_final_reply_over_token_budget_raises(self, tmp_skill):
        resp = ChatResponse(content="answer", usage=Usage(10, 15, 25))
        client = _client_returning(resp)
        a = Agent(tmp_skill(), client, budget=Budget(max_tokens=20))

        with pytest.raises(BudgetExceededError, match="exceeded budget after response"):
            a.run("question")

    def test_tool_batch_over_budget_raises_before_execution(self, tmp_skill):
        tool_resp = ChatResponse(
            content="",
            usage=Usage(5, 5, 10),
            tool_calls=[
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg":"a"}'},
                },
                {
                    "id": "tc-2",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg":"b"}'},
                },
            ],
        )
        client = _client_returning(tool_resp)
        a = Agent(tmp_skill(tools=["echo"]), client, budget=Budget(max_tool_calls=1))

        calls: list[str] = []

        class RecordingTool(EchoTool):
            def execute(self, args: dict) -> str:
                calls.append(args["msg"])
                return super().execute(args)

        a.tools.register(RecordingTool())

        with pytest.raises(BudgetExceededError, match="would exceed max_tool_calls"):
            a.run("test")
        assert calls == []

    def test_caps_max_tokens_to_remaining_budget(self, tmp_skill):
        resp = ChatResponse(content="ok", usage=Usage(1, 1, 2))
        client = _client_returning(resp)
        a = Agent(tmp_skill(), client, budget=Budget(max_tokens=8))

        a.send("hi")

        assert client.chat.call_args.kwargs["max_tokens"] < a.skill.max_tokens


class TestAgentCancel:
    def test_cancel_raises_cancelled_error(self, tmp_skill):
        tool_resp = ChatResponse(
            content="",
            usage=Usage(1, 1, 2),
            tool_calls=[{"id": "1", "function": {"name": "noop", "arguments": "{}"}}],
        )
        client = MagicMock(spec=Client)
        client.chat = MagicMock(return_value=tool_resp)
        a = Agent(tmp_skill(tools=["read_file"]), client)

        from pantheon.tools import Tool

        class CancelTrigger(Tool):
            def name(self):
                return "noop"

            def description(self):
                return ""

            def parameters(self):
                return {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                }

            def execute(self_, args):
                a.cancel()
                return "done"

        a.tools.register(CancelTrigger())
        with pytest.raises(CancelledError, match="cancelled"):
            a.run("hello")

    def test_deadline_raises_deadline_error(self, tmp_skill):
        import time

        def slow_chat(**kw):
            time.sleep(0.1)
            return ChatResponse(
                content="",
                usage=Usage(1, 1, 2),
                tool_calls=[{"id": "1", "function": {"name": "noop", "arguments": "{}"}}],
            )

        client = MagicMock(spec=Client)
        client.chat = MagicMock(side_effect=slow_chat)
        a = Agent(tmp_skill(), client, deadline_s=0.05)
        with pytest.raises(DeadlineExceededError, match="exceeded deadline"):
            a.run("work")

    def test_error_hierarchy(self):
        assert issubclass(BudgetExceededError, PantheonError)
        assert issubclass(DeadlineExceededError, PantheonError)
        assert issubclass(CancelledError, PantheonError)


class TestContextCompaction:
    def test_set_compactor_is_called_when_context_exceeds_threshold(self, tmp_skill) -> None:
        resp = ChatResponse(content="ok", usage=Usage(1, 1, 2))
        client = _client_returning(resp)
        a = Agent(tmp_skill(), client, context_limit=100)

        compactor = MagicMock(side_effect=lambda msgs: [msgs[0]])
        a.set_compactor(compactor)

        # 300 chars + 22-char system msg → 80 tokens → 80% utilization > 75%
        a.run("x" * 300)

        compactor.assert_called()
        assert a.context_tokens < 100

    def test_context_tokens_matches_history_content(self, tmp_skill) -> None:
        client = _client_returning()
        a = Agent(tmp_skill(), client, context_limit=1000)

        system_chars = len("You are test.")
        assert a.context_tokens == system_chars // 4

        a._history.append(Message(role="user", content="a" * 400))

        expected_tokens = (system_chars + 400) // 4
        assert a.context_tokens == expected_tokens
        assert a.context_utilization == pytest.approx(expected_tokens / 1000)

    def test_react_loop_continues_after_compaction(self, tmp_skill) -> None:
        tool_resp = ChatResponse(
            content="",
            usage=Usage(5, 5, 10),
            tool_calls=[
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "arguments": '{"msg":"' + "y" * 200 + '"}',
                    },
                }
            ],
        )
        final_resp = ChatResponse(content="done", usage=Usage(5, 5, 10))
        client = _client_returning(tool_resp, final_resp)

        a = Agent(tmp_skill(tools=["echo"]), client, context_limit=100)
        a.tools.register(EchoTool())

        compactor = MagicMock(
            side_effect=lambda msgs: [msgs[0]] + msgs[-2:],
        )
        a.set_compactor(compactor)

        result = a.run("x" * 200)

        assert result == "done"
        compactor.assert_called()
        assert client.chat.call_count == 2

    def test_no_compaction_when_under_threshold(self, tmp_skill) -> None:
        resp = ChatResponse(content="short", usage=Usage(1, 1, 2))
        client = _client_returning(resp)
        a = Agent(tmp_skill(), client, context_limit=128_000)

        compactor = MagicMock()
        a.set_compactor(compactor)

        a.run("hello")

        compactor.assert_not_called()


class TestLoadAll:
    def test_loads_skills_as_agents(self, tmp_path):
        skill_dir = tmp_path / "test_agent"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: myagent\ndescription: test\nmetadata:\n  persona: Tester\n---\n\n# Test"
        )

        client = MagicMock(spec=Client)
        agents = load_all(str(tmp_path), client)
        assert "myagent" in agents
        assert agents["myagent"].name == "myagent"


class TestEquipTools:
    def test_registers_matching_tools(self, tmp_skill):
        a = Agent(tmp_skill(tools=["echo"]), _client_returning())
        registry = Registry()
        registry.register(EchoTool())

        equip_tools(a, registry)
        assert a.tools.get("echo") is not None

    def test_warns_on_missing_tool(self, tmp_skill, caplog):
        a = Agent(tmp_skill(tools=["nonexistent"]), _client_returning())
        registry = Registry()

        with caplog.at_level("WARNING"):
            equip_tools(a, registry)
        assert "not found" in caplog.text

    def test_uses_builtins_by_default(self, tmp_skill):
        a = Agent(tmp_skill(tools=["read_file"]), _client_returning())
        equip_tools(a)
        assert a.tools.get("read_file") is not None

    def test_respects_allowed_tools(self, tmp_skill):
        a = Agent(
            tmp_skill(tools=["echo", "other"], allowed_tools=["echo"]),
            _client_returning(),
        )
        registry = Registry()
        registry.register(EchoTool())
        registry.register(_OtherTool())

        equip_tools(a, registry)
        assert a.tools.get("echo") is not None
        assert a.tools.get("other") is None
