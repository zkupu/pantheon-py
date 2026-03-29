# Repository Scripts

This folder captures reusable repository utilities.

Some scripts are operational helpers for the Pantheon repository itself. Others
are the model-access and benchmarking utilities created during recent
experiments.

They assume:

- `pantheon-py/.env` exists when you want to use local credentials
- `INFERENCE_API_KEY` is present in the environment or `.env`
- the script helpers accept either `GATEWAY_URL` or `NIM_BASE_URL` (no default — must be set explicitly)
- local benchmark scripts resolve `skillgrade` from `SKILLGRADE_CLI` or a nearby `skillgrade/dist/cli.js` checkout

The probe and benchmark helpers use shared inference rate limiting
when configured. The broad catalog probes default to conservative worker counts
and a `--max-models 100` safety cap.

## Operational utilities

- `doctor.py`: workspace health checks for repo root discovery, `.env` loading, import resolution, and required commands
- `install.py`: cross-platform installer for linking Pantheon skills, agents, and rules into `~/.cursor` (symlinks on Unix, junctions + copies on Windows)
- `secret_scan.py`: scan a tree for likely secrets and dangerous `eval()` / `exec()` usage
- `skill_validate.py`: validate roster consistency and script documentation, and summarize eval coverage gaps
- `sync_subagents.py`: sync portable subagent definitions (`.agents/subagents/`) to Cursor format (`.cursor/agents/`)

## Shared helper

- `thread_common.py`: shared env loading, catalog fetch, chat probe, and `skillgrade` benchmark helpers

## Examples

```bash
python scripts/doctor.py check
python scripts/install.py --check
python scripts/secret_scan.py .
python scripts/skill_validate.py validate
```
