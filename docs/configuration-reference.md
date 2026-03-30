# Configuration Reference

Pantheon loads configuration from environment variables, with optional `.env` file support.

## Environment Variables

| Variable | Purpose | Default | Fallback |
|----------|---------|---------|----------|
| `INFERENCE_API_KEY` | Primary API key for the inference gateway | (empty) | `API_KEY` |
| `GATEWAY_URL` | Base URL of the OpenAI-compatible API | (required) | — |
| `SKILLS_DIR` | Directory containing agent SKILL.md files | `.agents/skills` | `AGENTS_DIR`, then auto-discovery |
| `MEMORY_DIR` | Directory for session persistence files | `.memory` | — |
| `PANTHEON_AUDIT_LOG_PATH` | Optional path for tool audit logs | `.audit/tool-calls.jsonl` | — |
| `VERBOSE` | Enable detailed tool call logging | `false` | — |
| `API_KEY` | Backward-compatible alias for `INFERENCE_API_KEY` | — | — |
| `AGENTS_DIR` | Alias for `SKILLS_DIR` | — | — |
| `ANTHROPIC_API_KEY` | Anthropic API key; also used by skillgrade eval framework | — | — |
| `GEMINI_API_KEY` | Gemini provider key for skillgrade evals | — | — |
| `OPENAI_API_KEY` | OpenAI provider key for skillgrade evals | — | — |
| `NIM_API_KEY` | Used by eval/improvement scripts, not the main `pantheon` CLI | — | — |
| `NIM_BASE_URL` | Base URL for eval scripts; falls back to `GATEWAY_URL` | — | `GATEWAY_URL` |
| `NIM_MODEL` | Model for eval/improvement scripts | `azure/openai/gpt-4.1-mini` | — |

## `.env` File

Pantheon loads recognized Pantheon environment variables from a `.env` file at startup. It first checks the current working directory and then falls back to the discovered repository root when invoked from a subdirectory. The file format:

```bash
# Lines starting with # are comments
# Blank lines are ignored

GATEWAY_URL=https://api.openai.com/v1
INFERENCE_API_KEY=your-key-here
# Quotes are stripped automatically
SKILLS_DIR=".agents/skills"

# Existing environment variables are NOT overridden
VERBOSE=1

# Optional tool audit log path
# PANTHEON_AUDIT_LOG_PATH=.audit/tool-calls.jsonl
```

**Rules:**
- Lines starting with `#` are ignored
- Blank lines are ignored
- Values with `=` in them are supported (`KEY=value=with=equals`)
- Single and double quotes around values are stripped
- Unknown keys are ignored
- Existing environment variables take precedence (`.env` does not override)
- The nearest trusted project `.env` is used: current working directory first, then the discovered repository root

## Skills Directory Resolution

Pantheon searches for skills in this order:

1. `SKILLS_DIR` environment variable
2. `AGENTS_DIR` environment variable (alias)
3. Auto-discovery of first existing directory:
   - `.agents/skills`
   - `.cursor/skills`
   - `.claude/skills`
4. Bundled skills shipped inside published installs
5. Falls back to `.agents/skills`

## Gateway Configuration

The gateway client connects to any OpenAI-compatible chat completions API.

| Parameter | Value |
|-----------|-------|
| Endpoint | `{GATEWAY_URL}/chat/completions` |
| Auth | `Authorization: Bearer {INFERENCE_API_KEY}` |
| Timeout | 300 seconds per request |
| Retries | 3 attempts with exponential backoff for 429, 500, 502, 503, 504 errors |
| Streaming | Server-Sent Events (SSE) for real-time output |

`GATEWAY_URL` must be set to your OpenAI-compatible inference endpoint (e.g. `https://api.openai.com/v1`). There is no default. Pantheon requires HTTPS for remote gateways and only allows plain HTTP for localhost/loopback development.

### Anthropic API

The Python CLI speaks the OpenAI-compatible API format. Anthropic's native Messages API (`/v1/messages`) uses a different request/response format, so setting `GATEWAY_URL=https://api.anthropic.com/v1` directly is **not supported**.

To use Anthropic models with the Python CLI, install the LiteLLM extra:

```bash
pip install "pantheon[litellm]"
```

| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |

`ANTHROPIC_API_KEY` is included in the `api_key()` fallback chain after `INFERENCE_API_KEY` and `API_KEY`. When using LiteLLM, it auto-detects the key and routes to Anthropic's API with format translation.

## Rate Limiting

Pantheon applies shared request throttling when any `INFERENCE_RATE_LIMIT_*`
variable is set explicitly. You can also configure auto-enable for specific
hosts via `INFERENCE_RATE_LIMIT_HOSTS` (comma-separated hostnames).

| Variable | Default | Description |
|----------|---------|-------------|
| `INFERENCE_RATE_LIMIT_HOSTS` | (empty) | Comma-separated hostnames that auto-enable rate limiting when the gateway matches |
| `INFERENCE_RATE_LIMIT_PER_SECOND` | `4` | Max requests per second |
| `INFERENCE_RATE_LIMIT_PER_MINUTE` | `45` | Max requests per minute |
| `INFERENCE_RATE_LIMIT_PER_HOUR` | `900` | Max requests per hour |
| `INFERENCE_RATE_LIMIT_PER_DAY` | `7000` | Max requests per day |
| `INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN` | `0` (unlimited) | Max total requests per CLI invocation; `0` disables the per-run cap |
| `INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS` | `300` | Seconds before a cross-process lock file is considered stale and can be broken |
| `INFERENCE_RATE_LIMIT_STATE_DIR` | `~/.cache/inference-rate-limit` | Directory for cross-process rate limit state files (respects `$XDG_CACHE_HOME`) |
| `INFERENCE_RATE_LIMIT_DISABLE` | (unset) | Set to `1` to disable all rate limiting |

## Tool Restrictions

Built-in file and directory tools (`read_file`, `write_file`, `list_dir`, `search_files`) are restricted to the current working directory by default. `search_files` rejects parent-segment patterns such as `../*` and filters matches back through the allowed roots. Shell commands (`shell_exec`) are privileged, are not cwd-sandboxed, and run with a configurable timeout (default 60 seconds, set via `SHELL_EXEC_TIMEOUT`). Tool audit logging is best-effort: if the configured audit path is unavailable, tool execution still proceeds.

### Shell Execution

By default, `shell_exec` runs in **allow-list** mode: only commands whose
base name appears in the allow-list are permitted. A sensible default list
covers common development tools (`git`, `python`, `pip`, `pytest`, `ruff`,
`ls`, `cat`, `grep`, `find`, `mkdir`, `make`, `docker`, etc.). Dangerous
patterns (recursive root deletion, `mkfs`, piping downloads to shell) are
always blocked by the deny-list layer regardless of mode. Set
`SHELL_EXEC_MODE=deny-list` to revert to the legacy deny-list-only mode.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHELL_EXEC_MODE` | `allow-list` | Shell execution mode: `allow-list` (permits only listed commands, safer) or `deny-list` (blocks known-dangerous patterns, legacy) |
| `SHELL_EXEC_ALLOW_LIST` | *(built-in default)* | Comma-separated list of allowed command base names when `SHELL_EXEC_MODE=allow-list`; overrides the built-in default list when set |
| `SHELL_EXEC_TIMEOUT` | `60` | Maximum seconds for shell command execution |

## Budget Configuration

Budget limits can be set programmatically when creating agents:

```python
from pantheon import Agent, Budget

agent = Agent(skill, client, budget=Budget(
    max_usd=1.0,        # Maximum spend in USD
    max_tokens=100_000,  # Maximum total tokens
    max_tool_calls=50,   # Maximum tool invocations
))
```

Pantheon raises `BudgetExceededError` when a response or returned tool batch would cross a configured limit. Tool-call budgets are enforced before executing a returned tool batch; token and spend budgets are checked before the next request and after each response.

## Orchestration Defaults

| Parameter | Default | Description |
|-----------|---------|-------------|
| Operation deadline | 600s | Best-effort maximum wait time for Team/Pipeline/Review; already-running work is not forcibly canceled |
| Synthesis token limit | 100,000 | Max tokens in review synthesis prompt |
| ThreadPool workers | min(tasks, 8) | Bounded parallelism for fan-out operations |

## Model Configuration

### SKILL.md Model Names

Each SKILL.md declares a `model` field in its metadata. These names are resolved by the gateway at runtime. Example model identifiers:

| Model ID | Description | Use Case |
|----------|-------------|----------|
| `bedrock-claude-opus-4-6` | Claude Opus 4.6 via Bedrock | Deep reasoning, architecture, security |
| `gpt-5.3-codex` | GPT-5.3 Codex | Code generation, implementation |
| `nano` | Lightweight model | Fast tasks, formatting, style |

### Using Different Models

To use different model names (e.g., with Anthropic or OpenAI endpoints):

1. Set `GATEWAY_URL` and `INFERENCE_API_KEY` for your provider
2. Override the model in SKILL.md metadata

Model names are provider-specific. When switching gateways, update the `model` field in SKILL.md files to match your provider's model identifiers.

**Note for IDE agents**: The `model` field in SKILL.md metadata is consumed only by the Python CLI runtime. When running as an IDE agent (Cursor, Claude Code), the IDE's own model is used — SKILL.md model names are ignored.

### Default Fallback Model

Skills without an explicit `model` field in their SKILL.md metadata default to `meta/llama-3.3-70b-instruct` (see `skill.py:58`). All 24 bundled Pantheon skills specify their model explicitly, so this fallback only applies to user-created skills that omit the field.

### Compatibility Field

The `compatibility` field in SKILL.md frontmatter declares which environments a skill supports (e.g., `Cursor`, `Claude Code`, `OpenAI Codex`). This field is parsed and stored but **not currently used for filtering**. All skills are available in all environments. Future versions may use this for environment-aware skill discovery.
