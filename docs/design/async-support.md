# Design: Async Support

**Status:** Proposal
**Author:** Pantheon review backlog (Athena + Eris)
**Date:** 2026-03-29

## Problem

The Pantheon runtime uses synchronous I/O throughout:

- `gateway.py` uses `requests.Session` for HTTP (blocking per-request)
- `orchestrate.py` uses `ThreadPoolExecutor` for fan-out parallelism (thread-per-agent)
- `agent.py` ReAct loop is sequential within a single agent

Thread-based parallelism works but limits scalability. A `Review` with 5 agents spawns 5 threads, each blocking on HTTP I/O. Under orchestration patterns like `/rally` (7+ specialists), thread contention and memory overhead become non-trivial.

## Proposed Design

### Parallel Path: Sync + Async

Preserve the existing synchronous API for backwards compatibility. Add async variants alongside:

```python
# Existing (unchanged)
client = Client()
response = client.chat(messages, model="...")

# New async variant
async_client = AsyncClient()
response = await async_client.chat(messages, model="...")
```

### Gateway: `httpx.AsyncClient`

Replace `requests.Session` with `httpx.AsyncClient` in a new `AsyncClient` class:

```python
# gateway.py

class AsyncClient:
    """Async OpenAI-compatible gateway client."""

    def __init__(self, ...) -> None:
        self._session = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )

    async def chat(self, messages, model, ...) -> ChatResponse:
        ...

    async def chat_stream(self, messages, model, ...) -> AsyncIterator[str]:
        async with self._session.stream("POST", url, json=body) as resp:
            async for line in resp.aiter_lines():
                ...
```

Key changes:
- SSE parsing (`_parse_sse_chunk`) is pure and reusable as-is
- Retry logic (`_retry_delay`) is pure and reusable
- Connection pooling via `httpx.Limits` replaces `requests.Session` keep-alive
- `httpx` supports both sync and async from the same library

### Orchestration: `asyncio.TaskGroup`

Replace `ThreadPoolExecutor` with `asyncio.TaskGroup` in async orchestration:

```python
# orchestrate.py

class AsyncReview(Review):
    async def _run_parallel(self, agents, task):
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._run_agent(agent, task))
                for agent in agents
            ]
        return [t.result() for t in tasks]
```

Benefits:
- No thread overhead per agent
- Native cancellation via `TaskGroup` exception propagation
- Deadline enforcement via `asyncio.timeout()` instead of `FuturesTimeout`
- `contextvars` (used for delegation depth) propagate natively in async tasks

### Agent: Async ReAct Loop

```python
class AsyncAgent(Agent):
    async def run_stream(self, task, ...):
        while iteration < max_iter:
            response = await self._client.chat(self._history, self.model, ...)
            if tool_calls:
                results = await self._execute_tools(tool_calls)
            ...
```

Tool execution can be parallelized when multiple independent tool calls return in a single response.

## Migration Strategy

1. **Phase 1**: Add `httpx` as optional dependency (`pip install pantheon[async]`)
2. **Phase 2**: Implement `AsyncClient` in `gateway.py` alongside `Client`
3. **Phase 3**: Add `AsyncReview`, `AsyncPipeline`, `AsyncTeam` in `orchestrate.py`
4. **Phase 4**: Add `AsyncAgent` in `agent.py`
5. **Phase 5**: Update CLI commands to use async when available (detect event loop)

### Dependency Impact

- Add: `httpx>=0.27` (optional extra)
- Keep: `requests` (sync path unchanged)
- No breaking changes to existing API

## What Could Go Wrong

1. **Event loop conflicts** — if users embed Pantheon in an existing async app (e.g., FastAPI), nested event loops fail. Mitigation: never call `asyncio.run()` internally; let the caller manage the loop.

2. **Tool execution ordering** — some tools have side effects (write_file, shell_exec). Parallel async tool execution could introduce race conditions. Mitigation: execute tools sequentially by default; add `parallel_tools=True` opt-in.

3. **Streaming backpressure** — `httpx` async streaming with slow consumers can buffer unboundedly. Mitigation: use `resp.aiter_lines()` with bounded internal buffers.

4. **Testing complexity** — async tests require `pytest-asyncio` and different patterns. Mitigation: keep sync tests as the primary suite; async tests as a separate marker.

5. **SSE parsing edge cases** — `httpx` async line iteration may split SSE frames differently than `requests`. Mitigation: reuse the existing `_parse_sse_chunk` function (it operates on complete `data:` lines) and add integration tests.

## Decision

Recommended approach: parallel path with `httpx` optional dependency. This preserves zero-dependency simplicity for basic usage while enabling async for orchestration-heavy workloads. Start with Phase 1-2 (gateway only) and validate before tackling orchestration.
