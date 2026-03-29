"""Tests for the LLM gateway client — retry logic, SSE parsing, payload construction."""

import json
from unittest.mock import MagicMock, patch

import pytest

from pantheon.gateway import (
    ChatResponse,
    Client,
    Message,
    _retry_delay,
)


class TestRetryDelay:
    def test_exponential_backoff(self):
        d0 = _retry_delay(0)
        d1 = _retry_delay(1)
        d2 = _retry_delay(2)
        assert d0 < d1 < d2

    def test_respects_retry_after_header(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "42"}
        assert _retry_delay(0, resp) == 42.0

    def test_ignores_non_digit_retry_after(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "Thu, 01 Dec 2025 16:00:00 GMT"}
        delay = _retry_delay(0, resp)
        assert delay > 0
        assert delay != 42.0


class TestMessageToDict:
    def test_user_message(self):
        m = Message(role="user", content="hello")
        d = m.to_dict()
        assert d == {"role": "user", "content": "hello"}

    def test_assistant_with_tool_calls(self):
        tc = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "test", "arguments": "{}"},
            }
        ]
        m = Message(role="assistant", content="", tool_calls=tc)
        d = m.to_dict()
        assert d["content"] is None
        assert d["tool_calls"] == tc

    def test_assistant_with_content_and_tool_calls(self):
        tc = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "test", "arguments": "{}"},
            }
        ]
        m = Message(role="assistant", content="thinking...", tool_calls=tc)
        d = m.to_dict()
        assert d["content"] == "thinking..."
        assert d["tool_calls"] == tc

    def test_tool_result(self):
        m = Message(role="tool", content="result", tool_call_id="tc-1")
        d = m.to_dict()
        assert d["tool_call_id"] == "tc-1"

    def test_named_message(self):
        m = Message(role="system", content="sys", name="athena")
        d = m.to_dict()
        assert d["name"] == "athena"


class TestClientBuildPayload:
    def test_basic_payload(self):
        client = Client("http://test", "key")
        payload = client._build_payload("gpt-4o", [Message(role="user", content="hi")], 0.7, 4096)
        assert payload["model"] == "gpt-4o"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 4096
        assert len(payload["messages"]) == 1
        assert "tools" not in payload

    def test_payload_with_tools(self):
        client = Client("http://test", "key")
        tools = [{"type": "function", "function": {"name": "test"}}]
        payload = client._build_payload(
            "gpt-4o", [Message(role="user", content="hi")], 0.7, 4096, tools=tools
        )
        assert payload["tools"] == tools

    def test_payload_with_tool_choice(self):
        client = Client("http://test", "key")
        payload = client._build_payload(
            "gpt-4o",
            [Message(role="user", content="hi")],
            0.7,
            4096,
            tool_choice="auto",
        )
        assert payload["tool_choice"] == "auto"


class TestClientParseResponse:
    def test_simple_response(self):
        client = Client("http://test", "key")
        data = {
            "choices": [
                {
                    "message": {"content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        resp = client._parse_response(data)
        assert resp.content == "hello"
        assert resp.finish_reason == "stop"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.total_tokens == 15

    def test_tool_call_response(self):
        client = Client("http://test", "key")
        tc = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "echo", "arguments": '{"msg":"hi"}'},
            }
        ]
        data = {
            "choices": [{"message": {"content": "", "tool_calls": tc}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        resp = client._parse_response(data)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["function"]["name"] == "echo"

    def test_empty_choices(self):
        client = Client("http://test", "key")
        resp = client._parse_response({"choices": [{}], "usage": {}})
        assert resp.content == ""


class TestClientChat:
    def test_successful_chat(self):
        client = Client("http://test", "key", timeout=42)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        client.session.post = MagicMock(return_value=mock_resp)

        result = client.chat(model="test", messages=[Message(role="user", content="hello")])
        assert result.content == "hi"
        assert result.usage.total_tokens == 7
        assert client.session.post.call_args.kwargs["timeout"] == 42

    def test_retries_on_429(self):
        client = Client("http://test", "key")

        fail_resp = MagicMock()
        fail_resp.status_code = 429
        fail_resp.headers = {"Retry-After": "0"}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }

        client.session.post = MagicMock(side_effect=[fail_resp, ok_resp])
        with patch("pantheon.gateway._time.sleep"):
            result = client.chat(model="test", messages=[Message(role="user", content="hi")])
        assert result.content == "ok"
        assert client.session.post.call_count == 2

    def test_raises_on_non_retryable(self):
        client = Client("http://test", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.raise_for_status.side_effect = Exception("bad request")
        client.session.post = MagicMock(return_value=mock_resp)

        with pytest.raises(Exception, match="bad request"):
            client.chat(model="test", messages=[Message(role="user", content="hi")])


class TestClientStreamFull:
    @staticmethod
    def _sse_lines(*chunks: dict) -> list[str]:
        lines = []
        for c in chunks:
            lines.append(f"data: {json.dumps(c)}")
        lines.append("data: [DONE]")
        return lines

    def test_streams_content(self):
        client = Client("http://test", "key", timeout=21)
        chunks = [
            {"choices": [{"delta": {"content": "hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = self._sse_lines(*chunks)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        client.session.post = MagicMock(return_value=mock_resp)

        collected: list[str] = []
        result = client.chat_stream_full(
            model="test",
            messages=[Message(role="user", content="hi")],
            on_chunk=collected.append,
        )
        assert result.content == "hello"
        assert collected == ["hel", "lo"]
        assert client.session.post.call_args.kwargs["timeout"] == 21

    def test_streams_tool_calls(self):
        client = Client("http://test", "key")
        chunks = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "tc-1",
                                    "type": "function",
                                    "function": {"name": "echo", "arguments": '{"ms'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": 'g":"hi"}'},
                                }
                            ]
                        }
                    }
                ]
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = self._sse_lines(*chunks)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        client.session.post = MagicMock(return_value=mock_resp)

        result = client.chat_stream_full(
            model="test", messages=[Message(role="user", content="hi")]
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "tc-1"
        assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"msg": "hi"}

    def test_accumulates_usage_from_final_chunk(self):
        client = Client("http://test", "key")
        chunks = [
            {"choices": [{"delta": {"content": "ok"}}]},
            {
                "choices": [{"delta": {}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                },
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = self._sse_lines(*chunks)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        client.session.post = MagicMock(return_value=mock_resp)

        result = client.chat_stream_full(
            model="test", messages=[Message(role="user", content="hi")]
        )
        assert result.usage.prompt_tokens == 10
        assert result.usage.total_tokens == 13

    def test_retries_stream_on_503(self):
        client = Client("http://test", "key")

        fail_resp = MagicMock()
        fail_resp.status_code = 503
        fail_resp.headers = {}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.iter_lines.return_value = self._sse_lines(
            {"choices": [{"delta": {"content": "ok"}}]}
        )
        ok_resp.__enter__ = MagicMock(return_value=ok_resp)
        ok_resp.__exit__ = MagicMock(return_value=False)

        client.session.post = MagicMock(side_effect=[fail_resp, ok_resp])
        with patch("pantheon.gateway._time.sleep"):
            result = client.chat_stream_full(
                model="test", messages=[Message(role="user", content="hi")]
            )
        assert result.content == "ok"


class TestClientContextManager:
    def test_enter_returns_self(self):
        client = Client("http://test", "key")
        assert client.__enter__() is client

    def test_exit_closes_session(self):
        client = Client("http://test", "key")
        client.session = MagicMock()
        client.__exit__(None, None, None)
        client.session.close.assert_called_once()


class TestClientValidation:
    def test_raises_on_empty_api_key(self):
        with pytest.raises(ValueError, match="API key is required"):
            Client("http://test", "")

    def test_raises_on_none_api_key(self):
        with pytest.raises((ValueError, TypeError)):
            Client("http://test", None)  # type: ignore[arg-type]


class TestChatStream:
    def test_returns_content_string(self):
        client = Client("http://test", "key")
        with patch.object(client, "chat_stream_full") as mock:
            mock.return_value = ChatResponse(content="hello")
            result = client.chat_stream(
                model="test", messages=[Message(role="user", content="hi")]
            )
        assert result == "hello"
