"""Shared EchoTool for tests — importable module (conftest is not a regular import target)."""

from __future__ import annotations

from pantheon.tools import Tool, strict_schema


class EchoTool(Tool):
    def name(self) -> str:
        return "echo"

    def description(self) -> str:
        return "Echo"

    def parameters(self) -> dict:
        return strict_schema({"msg": {"type": "string", "description": "Message"}}, ["msg"])

    def execute(self, args: dict) -> str:
        return args["msg"]
