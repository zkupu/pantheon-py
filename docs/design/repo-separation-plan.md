# Repo Separation Plan: pantheon-py + pantheon

**Status:** Approved
**Date:** 2026-03-29
**Goal:** Split the monorepo into two independent repositories so the persona/skills layer is portable and the Python runtime stands alone.

## Repositories After Separation

| Repo | Purpose | Contents |
|------|---------|----------|
| `pantheon` | Portable agent framework (pure markdown, zero runtime deps) | CLAUDE.md, .agents/skills/, .agents/subagents/, AGENTS.md, eval suite, docs on persona system |
| `pantheon-py` | Local model execution engine (Python) | Python runtime, gateway, orchestration, CLI, tools, runtime docs, runtime tests |

## Current Entanglements

These are the coupling points that must be addressed during separation:

1. **Build-time bundling** -- `pyproject.toml` bundles `.agents/skills` into the wheel as `_bundled_skills`
2. **`config.py`** -- `_BUNDLED_SKILLS_DIR`, `skills_dir()`, `SKILLS_DIR`/`AGENTS_DIR` env vars, repo root detection via `.agents/skills`
3. **`skill.py`** -- `_SKILL_PATH_PATTERN` regex, `discover()`, `discover_map()`, `classify_agents()`
4. **`observe.py`** -- `ActivationTracker` references SKILL.md path pattern
5. **`orchestrate.py`** -- references `.agents/subagents/*.md` for output headings
6. **`cli.py`** -- `load_all(config.skills_dir(), ...)` for roster and classification
7. **`agent.py`** -- `load_all()` loads skills from directory
8. **`__init__.py`** -- exports `discover_skills`, `parse_skill`, `catalog`, `classify_agents`
9. **Makefile / tasks.py** -- lint, validate-skills, eval targets all reference `.agents/skills/`
10. **scripts/** -- `skill_validate.py`, `sync_subagents.py`, `doctor.py` operate on skills
11. **evals/** -- 22 skill evaluation directories with fixtures and graders
12. **tests/** -- `test_skill.py`, `test_repo_scripts.py`, others depend on skill files existing

## Waves

Each wave is a set of tasks that can run in parallel across separate Claude sessions. Waves are sequential -- wave N+1 depends on wave N being complete.

---

### Wave 0: Create the new repo and establish the bridge

**Prereq:** None
**Output:** Empty `pantheon` repo on GitHub with initial structure

#### Task 0.1: Create `pantheon` repo
- Create new GitHub repo `pantheon` (or `pantheon-agents` -- owner's call)
- Initialize with MIT license, README stub, .gitignore
- Create directory structure:
  ```
  pantheon/
  ├── .agents/
  │   ├── skills/       (will receive 24 skill dirs)
  │   └── subagents/    (will receive 10 subagent defs)
  ├── CLAUDE.md         (will receive portable persona)
  ├── AGENTS.md         (will receive routing/protocol doc)
  ├── evals/            (will receive eval suite)
  ├── scripts/          (will receive skill-related scripts)
  ├── docs/             (will receive persona/skill docs)
  ├── README.md
  └── LICENSE
  ```

#### Task 0.2: Design the bridge mechanism
- Add `PANTHEON_AGENTS_DIR` env var support to `pantheon-py` config (already partially exists as `SKILLS_DIR`)
- Document the contract: pantheon-py expects a directory containing `.agents/skills/` and `.agents/subagents/`
- **Decision: external-only. No bundling.** Integration options for users:
  1. `PANTHEON_AGENTS_DIR` env var (primary)
  2. Git submodule at `.agents/` (dev convenience)
  3. Symlink `.agents/` to a local checkout
- Document all three options with clear setup instructions in `pantheon-py` README

---

### Wave 1: Extract portable assets into `pantheon` repo

All tasks in this wave are independent and can run in parallel.

#### Task 1.1: Move skills
- Copy all 24 skill directories from `~/.agents/skills/` into `pantheon/.agents/skills/`
- Each contains a single `SKILL.md`
- Validate all SKILL.md files parse correctly after move

#### Task 1.2: Move subagents
- Copy all 10 subagent definitions from `~/.agents/subagents/` into `pantheon/.agents/subagents/`
- Validate all subagent markdown files are intact

#### Task 1.3: Move AGENTS.md
- Copy `AGENTS.md` from `pantheon-py/` into `pantheon/`
- Strip any pantheon-py-specific content (e.g., Python bootstrap commands like `python scripts/doctor.py claude-code`)
- Keep all routing tables, protocol, activation rules, dispatch patterns

#### Task 1.4: Create portable CLAUDE.md
- Create a `CLAUDE.md` in `pantheon/` that contains ONLY the persona layer:
  - Demeter identity and behavioral rules
  - Specialist domains routing table
  - Activation rule and protocol
  - Skill discovery pointing to `.agents/skills/<name>/SKILL.md`
  - Subagent dispatch patterns
  - Rally protocol
- Strip all pantheon-py-specific content (Python bootstrap, doctor.py, build references)

#### Task 1.5: Move eval suite
- Copy `evals/` directory into `pantheon/evals/`
- Includes: `_template/`, `bin/`, `README.md`, all 22 skill eval directories
- Update any paths in eval scripts that reference pantheon-py-specific locations
- Validate eval harness runs standalone (may need minor script adjustments)

#### Task 1.6: Move skill-related scripts
- Copy to `pantheon/scripts/`:
  - `skill_validate.py` -- validates SKILL.md format
  - `sync_subagents.py` -- syncs subagent definitions
- Leave in `pantheon-py/scripts/`:
  - `doctor.py` -- runtime health check (needs updating in Wave 2)
  - `install.py` -- runtime installer
  - `secret_scan.py` -- runtime security
  - `thread_common.py` -- runtime utility
- Scripts that move may need path adjustments to work standalone

#### Task 1.7: Move persona/skill documentation
- Move to `pantheon/docs/`:
  - Any docs that describe the skill system, persona framework, or agent routing
  - `docs/research/instruction-decay.md` (about prompt/instruction behavior, not runtime)
  - `docs/workflows.md` (workflow templates that invoke Pantheon specialists)
  - `docs/design/embedding-routing.md` (routing model design, persona concern)
- Keep in `pantheon-py/docs/`:
  - `cli-reference.md` -- runtime CLI
  - `configuration-reference.md` -- runtime config
  - `runtime-reference.md` -- runtime API
  - `troubleshooting.md` -- runtime troubleshooting
  - `docs/design/async-support.md` -- runtime design
  - `docs/design/sqlite-memory.md` -- runtime design

---

### Wave 2: Update `pantheon-py` to decouple from portable assets

All tasks in this wave are independent and can run in parallel.

#### Task 2.1: Update `config.py`
- Refactor `skills_dir()` to resolve skills via:
  1. `PANTHEON_AGENTS_DIR` env var (points to pantheon repo checkout)
  2. `SKILLS_DIR` env var (legacy, direct path to skills)
  3. Git submodule or symlink at `.agents/` (if present)
- **Remove `_BUNDLED_SKILLS_DIR` and all bundled-skills fallback logic**
- Update repo root detection to not depend on `.agents/skills` existing
- Add clear error message when no skills source is found, with setup instructions

#### Task 2.2: Update `pyproject.toml` build config
- **Remove** `.agents/skills` bundling from `[tool.hatch.build.targets.wheel.force-include]`
- **Remove** `.agents/` from `[tool.hatch.build.targets.sdist]` includes
- Skills are external-only -- the wheel ships without them

#### Task 2.3: Update Makefile and tasks.py
- Remove or conditionalize `.agents/skills/` from lint targets
- Remove `validate-skills` target (or make it check external dir)
- Remove or redirect eval targets to point at external eval suite
- Add `submodule-init` target for dev convenience

#### Task 2.4: Update tests
- `test_skill.py` -- mock or fixture the skills directory instead of depending on `.agents/skills/` existing
- `test_repo_scripts.py` -- update to handle missing skills gracefully
- Other tests -- audit for implicit skill directory dependencies
- Add test for `PANTHEON_AGENTS_DIR` config resolution

#### Task 2.5: Update `observe.py` and `orchestrate.py`
- `observe.py` -- ensure `ActivationTracker` works with configurable skills path
- `orchestrate.py` -- update subagent path references to use config rather than hardcoded `.agents/subagents/`

#### Task 2.6: Update `pantheon-py` CLAUDE.md
- Rewrite to focus on the Python runtime project
- Reference the `pantheon` repo for persona/skills
- Keep dev-specific instructions (build, test, lint commands)
- Remove the full persona definition (now lives in `pantheon/CLAUDE.md`)

#### Task 2.7: Update scripts and doctor.py
- `doctor.py` -- add check for skills source (env var, submodule, or bundled)
- Remove references to scripts that moved to `pantheon/`
- Add dev setup instructions for linking to `pantheon` repo

---

### Wave 3: Validate and ship

Sequential -- run after Waves 1 and 2 are both complete.

#### Task 3.1: Validate `pantheon` repo standalone
- Run `skill_validate.py` against all skills in new repo
- Run eval suite from new repo
- Verify CLAUDE.md works when loaded by Claude Code from the new repo root
- Verify `.agents/` structure is discovered correctly

#### Task 3.2: Validate `pantheon-py` with external skills
- Set `PANTHEON_AGENTS_DIR` to point at `pantheon/` checkout
- Run full test suite: `make check`
- Build wheel and verify it works (no bundled skills)
- Run `doctor.py` and verify it reports correct status
- Verify clear error when no skills source is configured

#### Task 3.3: Validate `pantheon-py` with submodule
- Add `pantheon` as git submodule at `.agents/`
- Run full test suite
- Verify skills discovery works through submodule path

#### Task 3.4: Update READMEs
- `pantheon/README.md` -- what it is, how to use with Claude Code, how to use with pantheon-py
- `pantheon-py/README.md` -- update to reference `pantheon` repo for skills, document setup options

#### Task 3.5: Clean up home directory
- Remove `~/.agents/skills/` and `~/.agents/subagents/` (now live in `pantheon/` repo)
- Update any symlinks or shell config that references old paths
- Update `~/CLAUDE.md` to source from `pantheon/` repo or symlink

---

## Session Assignment Matrix

For kicking off parallel Claude sessions:

| Session | Wave | Tasks | Summary |
|---------|------|-------|---------|
| A | 0 | 0.1, 0.2 | Create repo and design bridge |
| B | 1 | 1.1, 1.2, 1.3 | Move skills, subagents, AGENTS.md |
| C | 1 | 1.4, 1.5 | Create portable CLAUDE.md, move evals |
| D | 1 | 1.6, 1.7 | Move scripts and docs |
| E | 2 | 2.1, 2.2 | Update config.py and pyproject.toml |
| F | 2 | 2.3, 2.4 | Update Makefile/tasks.py and tests |
| G | 2 | 2.5, 2.6, 2.7 | Update observe/orchestrate, CLAUDE.md, scripts |
| H | 3 | 3.1, 3.2, 3.3, 3.4, 3.5 | Full validation and cleanup |

**Parallelism:**
- Wave 0: 1 session (A) -- must complete first
- Wave 1: 3 sessions (B, C, D) -- all parallel after Wave 0
- Wave 2: 3 sessions (E, F, G) -- all parallel after Wave 0 (can run alongside Wave 1 since they target different repos)
- Wave 3: 1 session (H) -- must wait for Waves 1 and 2

**Maximum parallelism: 6 sessions** (B, C, D, E, F, G all running simultaneously after Wave 0 completes)

## Resolved Decisions

1. **Repo name**: `pantheon`
2. **Bundling strategy**: External-only. No skill bundling in the wheel. Users integrate via env var, submodule, or symlink.
3. **Eval suite ownership**: Moves entirely to `pantheon` -- evals test skill content, not runtime behavior.
4. **`embedding-routing.md`**: Moves to `pantheon` -- routing model is a persona concern; pantheon-py implements it.
5. **`workflows.md`**: Moves to `pantheon` -- pure specialist workflow templates, no runtime content.
