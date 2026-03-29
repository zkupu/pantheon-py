# Contributing to Pantheon

### Virtual environment

Create and activate a virtual environment (required on Ubuntu 22.04+):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

All subsequent `pip`, `pytest`, `ruff`, and `pantheon` commands assume the venv is active.

## Setup (Linux / macOS / WSL)

```bash
git clone <repo-url>
cd pantheon-py
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/install.py          # link skills/agents/rules into ~/.cursor
```

## Setup (Windows — native)

```powershell
git clone <repo-url>
cd pantheon-py
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/install.py          # uses junctions + copies (or symlinks with Developer Mode)
```

> **Windows prerequisites**: Python 3.10+, Git, and Node.js (for the screenshot
> MCP server). Enable Developer Mode in Windows Settings → For Developers if
> you want native symlinks; otherwise the installer uses directory junctions and
> file copies.

The installer detects your platform automatically. Run `python scripts/install.py --check`
to preview what it would do without making changes.

## Development Loop

### Unix (make)

```bash
make check    # runs lint + tests
make test     # tests only
make lint     # lint only
make validate-skills
make doctor
```

### Any platform (tasks.py)

```bash
python tasks.py check         # lint + validate + test
python tasks.py test          # tests only
python tasks.py lint          # lint only
python tasks.py validate      # validate skill rosters
python tasks.py doctor        # workspace health checks
python tasks.py clean         # remove build artifacts
```

`tasks.py` is a cross-platform alternative to the Makefile. Both are kept in
sync — use whichever matches your environment.

Local skillgrade evals load the repo `.env` when present and reuse
`INFERENCE_API_KEY`/`GATEWAY_URL` as `NIM_API_KEY`/`NIM_BASE_URL` when the
NIM-specific variables are unset. They default `NIM_MODEL` to
`azure/openai/gpt-4.1-mini` unless you override it.

CI is not currently configured for this repository. Run tests locally with `make check`.

### Dependency lockfile

`requirements.lock` pins exact dependency versions with integrity hashes.
Regenerate after changing `pyproject.toml` dependencies:

```bash
pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml
```

CI uses the lockfile for reproducible installs. Local development can use
`pip install -e ".[dev]"` for flexibility.

### Pre-commit hooks

Install pre-commit hooks for automatic linting:

```bash
pip install pre-commit
pre-commit install
```

## Code Style

- Python 3.10+, type hints everywhere
- Ruff for linting (config in `pyproject.toml`)
- No unnecessary comments — code should be self-documenting
- Docstrings on modules and public classes/functions

## Tests

- pytest with class-based organization
- Use `unittest.mock` for external dependencies (HTTP, filesystem)
- Name pattern: `test_<module>.py` with `Test<Class>` groups
- Run `make test` before pushing

## Adding a New Agent Skill

1. Create `.agents/skills/<name>/SKILL.md`
2. Include YAML frontmatter with `name`, `description`, and `metadata`
3. The markdown body becomes the agent's system prompt
4. Add the agent to the roster in `AGENTS.md` and `.cursor/rules/pantheon.mdc`
5. Add an eval under `evals/<name>/` when practical for the skill

## Adding a Repository Utility Script

1. Add the script under `scripts/`
2. Document it in `scripts/README.md`
3. Add tests under `tests/`
4. If it enforces repository consistency, wire it into `make check`

## Adding a New Tool

1. Subclass `Tool` in `src/pantheon/tools.py` (or a new module)
2. Implement `name()`, `description()`, `parameters()`, `execute()`
3. Use `strict_schema()` for parameters to enforce strict mode
4. Register in `builtins()` if it should be available by default
5. Add tests

## Pull Requests

- One logical change per PR
- Tests must pass (`make check`)
- Update README if adding user-facing features
