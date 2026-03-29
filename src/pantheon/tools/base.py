"""Tool interface, registry, and schema helpers."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any

_log = logging.getLogger(__name__)


class Tool(ABC):
    """Abstract base class for all Pantheon tools.

    Subclasses implement name(), description(), parameters(), and execute()
    to define a tool that agents can invoke during a ReAct loop.
    """

    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def parameters(self) -> dict[str, Any]: ...

    @abstractmethod
    def execute(self, args: dict[str, Any]) -> str: ...

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name(),
                "description": self.description(),
                "parameters": self.parameters(),
                "strict": True,
            },
        }


class Registry:
    """Tool registration, lookup, and parallel execution.

    Stores Tool instances by name and dispatches tool calls from LLM
    responses, with argument validation and audit logging.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name()] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def definitions(self) -> list[dict[str, Any]]:
        return [t.definition() for t in self._tools.values()]

    def execute(self, name: str, args_json: str) -> str:
        from .audit import _audit_tool_call

        tool = self._tools.get(name)
        if not tool:
            return f"error: unknown tool '{name}'"
        t0 = time.monotonic()
        args: dict[str, Any] = {}
        try:
            args = json.loads(args_json) if args_json else {}
            missing = check_required(tool.parameters(), args)
            if missing:
                fields = ", ".join(missing)
                result = f"error: missing required fields for '{name}': {fields}"
                _audit_tool_call(name, args, result, time.monotonic() - t0, error=True)
                return result
            if err := _validate_args(tool.parameters(), args):
                _audit_tool_call(name, args, err, time.monotonic() - t0, error=True)
                return err
            result = tool.execute(args)
            _audit_tool_call(name, args, result, time.monotonic() - t0)
            return result
        except (
            json.JSONDecodeError,
            KeyError,
            ValueError,
            OSError,
            subprocess.SubprocessError,
        ) as e:
            _log.warning("tool '%s' failed: %s", name, e)
            _audit_tool_call(name, args, str(e), time.monotonic() - t0, error=True)
            return f"error: {e}"

    def execute_all(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        import contextvars
        from concurrent.futures import ThreadPoolExecutor

        ctx_snapshot = list(contextvars.copy_context().items())

        def run_one(call: dict) -> dict[str, Any]:
            tokens = [(var, var.set(val)) for var, val in ctx_snapshot]
            try:
                fn = call.get("function", {})
                result = self.execute(
                    fn.get("name", ""),
                    fn.get("arguments", ""),
                )
                return {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result,
                }
            finally:
                for var, token in tokens:
                    var.reset(token)

        with ThreadPoolExecutor(max_workers=min(len(calls), 8)) as pool:
            return list(pool.map(run_one, calls))


def param(desc: str, typ: str = "string") -> dict:
    return {"type": typ, "description": desc}


def check_required(schema: dict, args: dict) -> list[str]:
    """Return list of required fields missing from args."""
    required = schema.get("required", [])
    return [f for f in required if f not in args or args[f] is None]


def strict_schema(properties: dict, required: list[str]) -> dict:
    """Build a JSON Schema object with additionalProperties: false for strict mode."""
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _validate_args(schema: dict, args: dict) -> str | None:
    """Basic server-side argument validation. Returns error string or None."""
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(args) - set(properties)
        if extra:
            return f"error: unexpected arguments: {', '.join(sorted(extra))}"
    _type_map: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    for key, prop in properties.items():
        if key in args and "type" in prop:
            expected = _type_map.get(prop["type"])
            if expected and not isinstance(args[key], expected):
                return (
                    f"error: argument '{key}' must be {prop['type']},"
                    f" got {type(args[key]).__name__}"
                )
    return None
