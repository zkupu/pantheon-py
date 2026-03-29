# CLI Reference

The `pantheon` command provides all interaction modes for the toolkit.

## Commands

### `pantheon list`

Display all available agents in a formatted table.

```bash
pantheon list
```

Shows: name, persona, model, tool count, delegate count, and description for each agent discovered in the skills directory.

### `pantheon chat <agent>`

Interactive chat session with an agent. No tools — conversational only.

```bash
pantheon chat athena
```

- Messages stream in real-time
- Session history is persisted to `.memory/` on exit
- Restores previous session if one exists

**In-session commands:**

| Command | Action |
|---------|--------|
| `/reset` | Clear conversation history |
| `/save` | Save session to disk |
| `/quit` | Exit (auto-saves) |

### `pantheon ask <agent> <message>`

One-shot message to an agent. No tools, no history. Streams the response to stdout.

```bash
pantheon ask eris "Why microservices?"
pantheon ask athena "What patterns does this codebase use?"
```

### `pantheon run <agent> <task>`

Execute a task using the ReAct loop with tools enabled. The agent can read files, write files, execute shell commands, list directories, and search the codebase.

```bash
pantheon run kali "Audit this project for security issues"
pantheon run nuwa "Add type hints to src/utils.py"
```

Tool calls are displayed in the terminal as they execute. The final response is printed to stdout.

### `pantheon team <coordinator> <task>`

Hierarchical delegation. The coordinator agent receives the task and delegates to its configured specialists using the agent-as-tool pattern.

```bash
pantheon team freya "Design and implement a rate limiter"
```

The coordinator's delegates are defined in its SKILL.md under `metadata.delegates`. Each specialist runs its own ReAct loop with tools. The coordinator synthesizes the results.

### `pantheon pipe <agents> <input>`

Sequential pipeline. Output from each agent feeds as input to the next.

```bash
pantheon pipe athena,brigid,kali "Add structured logging to the API"
```

Agents are comma-separated. Each agent runs with tools enabled. If any stage fails, the pipeline stops with an error indicating which stage failed.

### `pantheon review <agents> <input>`

Parallel fan-out review. All agents except the last run their reviews simultaneously. The last agent synthesizes the results.

```bash
pantheon review kali,pele,themis,athena "Review for production readiness"
```

The last agent in the comma-separated list is the synthesizer. All others are reviewers that run in parallel. Reviewer weights are carried into the synthesis prompt.

### `pantheon auto <task>`

Automatically classify a task against the agent roster, select the best agents, pick an orchestration topology, and execute — all in one command.

```bash
pantheon auto "Audit this project for security vulnerabilities"
pantheon auto "Add retry logic to the HTTP client" --lead athena
pantheon auto "Review the CI pipeline for flaky tests" --dry-run
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--lead` | `demeter` | Agent that synthesizes results when multiple specialists are selected |
| `--dry-run` | off | Show the routing plan (agents, scores, topology) without executing |

**Behavior:**

1. Loads all agents and calls `classify_agents()`, which scores each agent by matching its `routing_signals` against the task text using word-boundary matching. Agents with a score > 0 are returned, highest first. Demeter is removed from results when other specialists match.
2. **No matches** — prints a warning and falls back to running the `--lead` agent directly.
3. **Single match** — routes the task to that specialist and runs its ReAct loop with tools.
4. **Multiple matches** — dispatches all matched specialists in parallel, then the `--lead` agent synthesizes their outputs. The topology is selected automatically by `select_topology()` based on dependency structure (parallel, sequential, hierarchical, or hybrid). When parallel, this is equivalent to `pantheon review`.

With `--dry-run`, the command prints each matched agent's name, score, and persona, the planned topology, and exits without calling any models.

### `pantheon warroom`

Interactive War Room — address any agent by name, broadcast to all.

```bash
pantheon warroom
```

Also launches when no subcommand is provided (`pantheon` with no args).

**War Room commands:**

| Command | Action |
|---------|--------|
| `@<name> <msg>` | Speak to a specific agent |
| `/all <msg>` | Broadcast to all agents in parallel |
| `/list` | Show all available agents |
| `/quit` | Exit the War Room |

Agents with tools configured use the ReAct loop. Agents without tools respond conversationally.

## Global Behavior

- All commands load recognized Pantheon configuration from `.env` if present (see [Configuration Reference](configuration-reference.md))
- File and directory tools are restricted to the current working directory by default
- `shell_exec` is a privileged tool and is not sandboxed to the working directory
- `VERBOSE=1` enables detailed tool call logging in `pipe` and `review` commands
- Orchestration commands use a best-effort 600-second deadline; timing out stops waiting but does not forcibly cancel already-running work
