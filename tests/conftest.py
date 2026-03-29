"""Shared test fixtures for the Pantheon test suite."""

# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pantheon.agent import Agent
from pantheon.gateway import ChatResponse, Client, Usage
from pantheon.skill import Metadata, Skill
from tests.echo_tool import EchoTool


@pytest.fixture
def echo_tool():
    return EchoTool()


@pytest.fixture
def tmp_skill():
    """Factory for creating test skills with configurable attributes."""

    def _make(
        name: str = "test",
        tools: list[str] | None = None,
        delegates: list[str] | None = None,
        max_iterations: int = 5,
        allowed_tools: list[str] | None = None,
        routing_signals: list[str] | None = None,
    ) -> Skill:
        return Skill(
            name=name,
            description=f"{name} skill",
            body=f"You are {name}.",
            path=f"/test/{name}/SKILL.md",
            metadata=Metadata(
                persona=f"{name.title()} Persona",
                model="test-model",
                temperature=0.5,
                max_tokens=1024,
                max_iterations=max_iterations,
                tools=tools or [],
                delegates=delegates or [],
                allowed_tools=allowed_tools or [],
                routing_signals=routing_signals or [],
            ),
        )

    return _make


@pytest.fixture
def mock_client():
    """Factory for creating mock clients that return a fixed reply."""

    def _make(reply: str = "ok") -> Client:
        resp = ChatResponse(content=reply, usage=Usage(1, 1, 2))
        client = MagicMock(spec=Client)
        client.chat = MagicMock(return_value=resp)
        client.chat_stream = MagicMock(return_value=reply)
        client.chat_stream_full = MagicMock(return_value=resp)
        return client

    return _make


@pytest.fixture
def tmp_agent(tmp_skill, mock_client):
    """Factory for creating test agents with a mock client."""

    def _make(
        name: str = "test",
        reply: str = "ok",
        tools: list[str] | None = None,
        delegates: list[str] | None = None,
        max_iterations: int = 5,
        allowed_tools: list[str] | None = None,
        routing_signals: list[str] | None = None,
    ) -> Agent:
        return Agent(
            tmp_skill(
                name,
                tools,
                delegates,
                max_iterations,
                allowed_tools=allowed_tools,
                routing_signals=routing_signals,
            ),
            mock_client(reply),
        )

    return _make
