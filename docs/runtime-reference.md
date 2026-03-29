# Pantheon Runtime Reference

Python runtime features, CLI commands, and orchestration topologies for the Pantheon toolkit.

## Automatic Routing

The `pantheon auto` command classifies a task description against each agent's `routing_signals` and dispatches work to the best-matching specialists automatically:

```bash
pantheon auto "Review this codebase for security issues and code quality"
# → routes to [kali, themis] → demeter (synthesize)

pantheon auto "Write a Python script to parse CSV data"
# → routes to [nuwa, seshat] → demeter (synthesize)

pantheon auto --dry-run "Review this project for security issues"
# → shows: kali (score=1), without executing
```

Each skill declares `routing_signals` in its YAML frontmatter — a list of keywords and phrases the classifier matches against:

```yaml
metadata:
  routing_signals:
    - security
    - vulnerability
    - threat model
```

When one agent matches, it runs directly. When multiple match, they fan out in parallel (Review topology) with the lead agent synthesizing results. The auto command always uses parallel fan-out — for sequential or hierarchical workflows, use `pantheon pipe` or `pantheon team` with explicit agent selection. Use `--lead` to override the synthesizer, `--dry-run` to preview routing.

## Orchestration Topologies

The runtime supports four execution patterns, selected adaptively based on task dependency structure:

| Topology | When | CLI |
|----------|------|-----|
| Parallel | Parallel reviewers followed by a synthesis step | `pantheon review` |
| Sequential | Ordered chain, each feeds the next | `pantheon pipe` |
| Hierarchical | Coordinator delegates to specialists | `pantheon team` |
| Hybrid | Mix — parallel first, then sequential | (adaptive) |
| Auto | Classifier picks agents, parallel fan-out + synthesis | `pantheon auto` |

## CLI Commands

| Command | Mode | Description |
|---------|------|-------------|
| `pantheon list` | — | Show all available agents |
| `pantheon chat <agent>` | Interactive | Multi-turn conversation, no tools, session persistence (`/save`, `/reset`, `/quit`) |
| `pantheon ask <agent> <msg>` | One-shot | Single message, no tools, no persistence |
| `pantheon run <agent> <task>` | ReAct | Full tool-using loop with reasoning |
| `pantheon team <coord> <task>` | Hierarchical | Coordinator delegates to specialists via agent-as-tool |
| `pantheon pipe <a,b,c> <input>` | Sequential | Output of each agent feeds into the next |
| `pantheon review <a,b,...,synth> <input>` | Parallel | Fan-out to reviewers, last agent synthesizes |
| `pantheon auto <task>` | Adaptive | Classify task, auto-select agents, parallel fan-out |
| `pantheon` (no args) | War Room | Interactive multi-agent session: `@name msg`, `/all msg`, `/list`, `/quit` |

## Runtime Features

**Rate Limiting**: Shared cross-process throttle with four time windows (per-second, per-minute, per-hour, per-day). Auto-enabled for hosts listed in `INFERENCE_RATE_LIMIT_HOSTS`, or when any `INFERENCE_RATE_LIMIT_*` variable is set. Disable with `INFERENCE_RATE_LIMIT_DISABLE=1`.

**Budget Tracking**: Three-axis budget enforcement (USD, tokens, tool calls) checked before and after each LLM call. Set via `Budget(max_usd=, max_tokens=, max_tool_calls=)` in the Python API.

**Session Memory**: File-backed conversation persistence in `.memory/`. Supports `WindowTrimmer` (keep last N messages) and `SummaryCompressor` (LLM-generated summaries) for context management. Three tiers: orchestrator, agent, shared.

**Audit Logging**: Structured JSONL trail of all tool invocations in `.audit/tool-calls.jsonl`. Includes timestamps, sanitized arguments, result SHA-256 hash, elapsed time. Sensitive fields auto-redacted. Configure path via `PANTHEON_AUDIT_LOG_PATH`.

**Context Management**: Automatic compaction when context utilization exceeds 75%. Pluggable compactors via `agent.set_compactor()`.

**Shell Safety**: Destructive commands (rm -rf /, mkfs, piping downloads to shell) are blocked by a deny-pattern list. File tools are scoped to the current working directory by default.

**Delegation Guard**: Agent-as-tool delegation is depth-limited to 3 levels to prevent circular delegation loops. Uses `contextvars` for thread-safe depth tracking across parallel fan-outs.

**Deadline & Cancellation**: Team, Pipeline, and Review orchestrators enforce a configurable deadline (default 600s). Individual agents support per-agent deadlines via `deadline_s`. On timeout, running agents receive a cancellation signal via `threading.Event`, checked at each ReAct iteration. Remaining stages or reviewers are cancelled and a `DeadlineExceededError` is raised.

**Error Hierarchy**: All runtime errors inherit from `PantheonError`, enabling structured error handling: `BudgetExceededError`, `DeadlineExceededError`, `DelegationDepthError`, `CancelledError`.
