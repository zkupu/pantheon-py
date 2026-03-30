# Troubleshooting

Common issues and solutions when using the Pantheon toolkit.

## Gateway / API Connection

### `RuntimeError: GATEWAY_URL environment variable is required`

Set the gateway URL in your `.env` or environment:

```bash
export GATEWAY_URL=https://api.openai.com/v1
```

### `ValueError: API key is required`

At least one of these must be set: `INFERENCE_API_KEY`, `API_KEY`, or `ANTHROPIC_API_KEY`.

```bash
export INFERENCE_API_KEY=your-key-here
```

### `ValueError: gateway URL must use https unless it targets localhost/loopback`

Non-HTTPS gateway URLs are only accepted for `localhost`, `127.0.0.1`, or `::1`. For remote endpoints, use `https://`.

### HTTP 401 / Authentication errors

Check that your API key is valid and matches the provider at `GATEWAY_URL`. The `resolve_model()` function applies provider prefixes for `sk-` keys automatically — if using a non-standard key format, ensure the model name includes the full provider prefix (e.g., `azure/openai/gpt-4.1-mini`).

## Rate Limiting

### `RateLimitExceededError`

The per-run request cap (`INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN`) was hit. Increase it or set to `0` to disable:

```bash
export INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN=0
```

### Rate limiting not activating from `.env`

Ensure `INFERENCE_RATE_LIMIT_HOSTS` is set in your `.env` file. All rate limit variables are loaded from `.env` at startup.

### Stale lock files

If Pantheon hangs acquiring a rate limit lock, a previous process may have crashed without cleanup. Locks older than `INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS` (default 300s) are automatically broken. To force cleanup:

```bash
rm -rf ~/.cache/inference-rate-limit/*.lock
```

## Budget / Limits

### `BudgetExceededError`

The agent exceeded its configured budget (USD, tokens, or tool calls). Increase limits in the `Budget()` constructor or via the CLI `--budget-*` flags.

### `DeadlineExceededError`

An orchestration topology (Team, Pipeline, Review) exceeded its deadline (default 600s). Pass a longer `deadline_s` or simplify the task.

## Shell Execution

### `error: command '<cmd>' not in allow-list`

The default shell execution mode is `allow-list`. Only pre-approved commands are permitted. To add a command:

```bash
export SHELL_EXEC_ALLOW_LIST=git,python3,pip,make,your-command
```

Setting this replaces the entire default list, so include all commands you need.

### `error: command contains shell metacharacters`

In allow-list mode, shell chaining (`;`, `|`, `&`, `` ` ``, `$(`) is blocked. Run commands individually instead of chaining them.

### `error: command blocked by safety policy — matches deny pattern`

Destructive commands (`rm -rf /`, `mkfs`, piping downloads to shell) are always blocked regardless of mode.

### `error: command accesses a secrets file (.env)`

Commands that read `.env` files via `cat`, `grep`, etc. are blocked. Use `read_file` with the appropriate tool instead, or access env vars via `os.environ` in Python.

## Agent / Skill Discovery

### No agents found / empty `pantheon list`

Ensure your working directory or `SKILLS_DIR` points to a directory containing SKILL.md files:

```bash
# Check current discovery path
python3 -c "from pantheon.config import skills_dir; print(skills_dir())"
```

Skills are discovered from (in order):
1. `SKILLS_DIR` or `AGENTS_DIR` environment variable
2. `.agents/skills/` relative to current directory
3. `.agents/skills/` relative to repository root
4. Bundled skills (when installed as a package)

## WSL 2 Performance

### Slow file operations on `/mnt/c/`

The 9P protocol used by WSL 2 to access Windows filesystems is ~10x slower than native Linux I/O. Clone repositories into the Linux filesystem:

```bash
cd ~
git clone <repo-url> my-project  # NOT into /mnt/c/
```

## Anthropic API Compatibility

### Tool call format errors with Anthropic models

The Pantheon gateway speaks the OpenAI `/chat/completions` format. Anthropic's native Messages API uses a different format. Install LiteLLM for automatic translation:

```bash
pip install "pantheon[litellm]"
export ANTHROPIC_API_KEY=sk-ant-...
```
