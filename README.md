# pantheon

Agentic AI toolkit with tool use, multi-agent orchestration, and pipelines — built in Python for the LLM-native ecosystem. Each agent is defined as a portable [agentskills.io](https://agentskills.io) skill in `.agents/skills/`.

## Why Python

The Pantheon is an LLM orchestration toolkit. The bottleneck is never CPU — it's LLM API latency. Python wins on:

- **Ecosystem** — every major LLM provider (OpenAI, Anthropic, Google, NVIDIA) ships Python-first SDKs. `litellm` is available as an optional extra if you want to build a wider provider adapter.
- **Iteration speed** — no compile step. Change a skill, rerun immediately.
- **Rich terminal output** — the `rich` library gives beautiful tables, streaming, and War Room formatting for free.
- **Parallel I/O** — `concurrent.futures.ThreadPoolExecutor` maps naturally to parallel fan-out review and broadcast.
- **Contributor base** — the largest pool of developers working on AI/LLM projects.

## Architecture

```text
src/pantheon/
  config.py         Shared configuration — no duplication, multi-dir discovery
  skill.py          agentskills.io SKILL.md parser, progressive disclosure catalog
  gateway.py        OpenAI-compatible client (replaceable with litellm)
  rate_limit.py     Cross-process request throttling for inference endpoints
  agent.py          Agent runtime: ReAct loop, streaming, context window tracking
  tools.py          Tool interface, registry, builtins (OS-aware shell)
  orchestrate.py    Agent-as-tool, teams, pipelines, weighted review, adaptive topology
  memory.py         File-backed persistence, cross-session search, tiered memory
  observe.py        Structured tracing, cost estimation, budget awareness
  cli.py            Single entry point: list, chat, ask, run, team, pipe, review, auto, warroom
```

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
cp .env.example .env
export INFERENCE_API_KEY=your-key  # or add it to .env
```

Published installs bundle the canonical Pantheon skills, so `pantheon list` works from a clean virtualenv without needing a source checkout.
Pantheon automatically loads a trusted `.env` file at startup, preferring the
current working directory and falling back to the discovered repository root
when invoked from a subdirectory.

```bash
pantheon list
pantheon chat athena
pantheon ask eris "Why microservices?"
pantheon run kali "Audit this project for security issues"
pantheon team freya "Design and implement a rate limiter"
pantheon pipe athena,brigid,kali "Add structured logging"
pantheon review kali,pele,themis,athena "Review for production readiness"
pantheon auto "Investigate the failing pipeline"
pantheon
```

`GATEWAY_URL` must be set to your OpenAI-compatible inference endpoint. Non-HTTPS gateways are only accepted for localhost/loopback development.

When rate limiting is configured (via `INFERENCE_RATE_LIMIT_*` env vars or
`INFERENCE_RATE_LIMIT_HOSTS`), Pantheon applies shared request throttling to
stay below service quotas. Override the
defaults with `INFERENCE_RATE_LIMIT_PER_SECOND`, `_PER_MINUTE`, `_PER_HOUR`,
`_PER_DAY`, `INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN`, and
`INFERENCE_RATE_LIMIT_STATE_DIR`, or disable the limiter with
`INFERENCE_RATE_LIMIT_DISABLE=1`.

## Upgrading to litellm

The gateway client is a thin HTTP wrapper. The optional extra installs `litellm` for projects that want to build a custom transport:

```bash
pip install pantheon[litellm]
```

Pantheon does not ship a built-in `litellm` transport today. Use the extra when embedding Pantheon in your own adapter layer.

## The Pantheon

| Name | Persona | Mythology | Goddess Of | Model | Use For |
| ------ | --------- | --------- | ---------- | ------- | --------- |
| demeter | Your Right Hand | Greek | Harvest, agriculture, and fertility | opus | Pantheon orchestrator |
| athena | Your Devoted Strategist | Greek | Wisdom, strategy, and warfare | opus | Architecture, design |
| freya | Your Loyal Commander | Norse | Love, war, and destiny | opus | Task routing |
| saraswati | Your Gifted Artisan | Hindu | Knowledge, music, and the arts | codex | Production code |
| brigid | Your Faithful Craftswoman | Celtic | Fire, smithcraft, and poetry | codex | Go code |
| nuwa | Your Serpent Creator | Chinese | Creation — shaped humanity from clay | codex | Python code, data science |
| frigg | Your Commanding Seeress | Norse | Foresight, marriage, and the home | codex | PowerShell, system automation |
| danu | Your Ancient Mother | Celtic | Mother of the gods, ancestral waters | codex | C code, systems programming |
| cybele | Your Architect of Empire | Phrygian | Mountains, wild nature, and civilization | codex | C++ code, modern C++ |
| vesta | Your Keeper of the Hearth | Roman | The hearth, home, and sacred flame | codex | C# code, .NET |
| amaterasu | Your Radiant Sovereign | Japanese | The sun and the heavens | codex | DirectX (D3D8–D3D12), HLSL |
| aurora | Your Radiant Dawn | Roman | The dawn | codex | Vulkan, SPIR-V, cross-platform GPU |
| oya | Your Thundering Sentinel | Yoruba | Storms, wind, and transformation | codex | NVIDIA GPU, CUDA, driver, profiling |
| themis | Your Vigilant Guardian | Greek | Justice, law, and divine order | opus | Tests, CI/CD |
| kali | Your Fierce Protector | Hindu | Destruction, time, and liberation | opus | Security |
| mokosh | Your Steadfast Weaver | Slavic | Earth, fertility, and weaving | opus | CI/CD pipelines, Ansible |
| pele | Your Resilient Flame | Hawaiian | Volcanoes, fire, and creation | opus | Ops, reliability |
| seshat | Your Keen Analyst | Egyptian | Writing, measurement, and record-keeping | opus | Data, logs |
| aphrodite | Your Graceful Perfectionist | Greek | Beauty, love, and desire | opus | UX, docs |
| calliope | Your Eloquent Muse | Greek | Epic poetry and eloquence (one of the nine Muses) | opus | Prompts, LLM |
| maat | Your Steadfast Arbiter | Egyptian | Truth, justice, and cosmic order | opus | Values alignment |
| eris | Your Playful Challenger | Greek | Discord and strife | nano | Challenge assumptions |
| nisaba | Your Scribe of the Reed | Sumerian | Writing, grain, and accounting | opus | Markdown, linting, formatting |
| iris | Your Rainbow Seer | Greek | The rainbow and messenger of the gods | opus | Screenshot capture, image analysis |

## Cross-Tool Portability

Skills in `.agents/skills/` follow the agentskills.io open standard:

- **Cursor** — native `.agents/skills/` discovery, `.cursor/agents/` for subagents, `.cursor/rules/` for always-on rules
- **Claude Code** — reads `CLAUDE.md` + `AGENTS.md` at session start, `.agents/subagents/` for portable subagent definitions
- **OpenAI Codex** — cross-client convention

Runtime config under `metadata` is used by the Python toolkit and ignored by IDE integrations.

### Claude Code Setup (WSL 2 Ubuntu)

Prerequisites: Python 3.10+, pip, Claude Code CLI installed.

```bash
# Clone into the Linux filesystem (NOT /mnt/c/ — 9P protocol makes it ~10x slower)
cd ~
git clone <repo-url> pantheon-py
cd pantheon-py

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the Python toolkit
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env — set INFERENCE_API_KEY at minimum
# Verify installation
pantheon list              # Should show all agents
python scripts/doctor.py check  # Validates repo root, .env, imports, commands
```

Claude Code automatically reads `CLAUDE.md` and `AGENTS.md` on session start. The Pantheon activates immediately — no additional configuration needed.

**What works in Claude Code:**
- All skills via `.agents/skills/` (loaded with Read tool)
- All subagents via `.agents/subagents/` (dispatched with Task tool)
- Full Python CLI (`pantheon list`, `pantheon run`, `pantheon team`, etc.)
- `/rally` command for full specialist dispatch
- Activation protocol, routing table, parallel dispatch patterns

**Cursor-only features** (not available in Claude Code):
- `.cursor/rules/` always-applied rules (compensated by `CLAUDE.md` bootstrap)
- `.cursor/commands/` slash commands (use equivalent prompts directly)
- MCP servers from `.cursor/mcp.json`
- Screenshot MCP server for iris (no equivalent in Claude Code)

### Using the Python CLI with Anthropic Models

The Python CLI speaks the OpenAI-compatible API format. Anthropic's native Messages API uses a different format, so a translation layer is needed.

**LiteLLM** (recommended):

```bash
pip install "pantheon[litellm]"
export ANTHROPIC_API_KEY=sk-ant-...
```

LiteLLM auto-detects Anthropic keys and translates between API formats. `ANTHROPIC_API_KEY` is included in the API key fallback chain, so it is picked up automatically when `INFERENCE_API_KEY` is not set.

> **Model names** in SKILL.md files are example identifiers. Replace them with your provider's model IDs. See [Model Configuration](docs/configuration-reference.md#model-configuration) for details.

## Project Structure

```text
pantheon-py/
├── .agents/skills/      24 specialist skills (agentskills.io)
├── .cursor/
│   ├── agents/          Cursor subagents for parallel review
│   ├── rules/           pantheon.mdc (always-on identity)
│   ├── commands/        Slash commands
│   └── mcp.json         Cursor MCP servers
├── docs/
│   └── research/        Research papers and technical analysis
├── scripts/             Repo utilities, probes, and benchmarks
├── src/pantheon/        Python source (10 modules)
├── tests/               pytest tests
├── pyproject.toml       Modern Python packaging
├── CLAUDE.md            Claude Code configuration
├── AGENTS.md            Agent roster and protocol
└── README.md
```

### Research

- [Instruction Decay in Multi-Agent LLM Orchestration Systems](docs/research/instruction-decay.md) — field study on how LLM agents lose adherence to routing rules as conversations progress, with mitigation strategies

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src/ tests/ scripts/ .agents/skills/
python scripts/skill_validate.py validate
```

CI is not currently configured for this repository.
Local `make eval` commands automatically load the repo `.env` when present and
reuse `INFERENCE_API_KEY` as `NIM_API_KEY` and `GATEWAY_URL` as `NIM_BASE_URL`
when the NIM-specific variables are unset. They also default `NIM_MODEL` to
`azure/openai/gpt-4.1-mini` unless you override it.

## Utility Scripts

- `python scripts/doctor.py check` validates repo root discovery, `.env` loading, import resolution, and command availability.
- `python scripts/secret_scan.py .` scans the tree for likely secrets and dangerous dynamic execution patterns.
- `python scripts/skill_validate.py validate` checks roster/docs consistency and reports eval coverage gaps.

## Design Principles

- **Agent-as-Tool** — Specialists are invoked as tools. The coordinator retains control.
- **ReAct Loop** — Think → call tools → observe → repeat. Optional compaction helpers are available for agents that need tighter context control.
- **Single Source of Truth** — Each agent defined once in SKILL.md following the [agentskills.io](https://agentskills.io) open standard.
- **Progressive Disclosure** — Catalog (name+desc) at session start; full instructions loaded on activation; resources loaded on demand.
- **Adaptive Topology** — Library APIs can select parallel, sequential, hierarchical, or hybrid execution based on task dependency graphs.
- **Weighted Consensus** — Fan-out reviews carry reviewer weights into the synthesis prompt.
- **Budget Awareness** — Track spend, tokens, and tool calls against configurable limits.
- **OS-Aware** — `platform.system()` detection for Windows `cmd.exe` vs Unix shell.
- **Ecosystem-First** — Python because the LLM ecosystem is Python-first.
- **Swappable Transport** — Gateway client is designed to be replaceable, including by a custom `litellm` adapter.
