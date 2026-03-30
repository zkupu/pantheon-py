#!/usr/bin/env bash
# Wave 2: Update pantheon-py to decouple from portable assets
#
# Launches 3 parallel Claude Code sessions (E, F, G) targeting pantheon-py.
# Each session works in its own git worktree to avoid conflicts.
# Prereq: Wave 0 complete (bridge mechanism designed)
# Note: Can run in parallel with Wave 1 (different repos)
#
# Usage: ./scripts/wave2.sh [pantheon-dir]
#   pantheon-dir: path to pantheon repo (default: sibling of pantheon-py)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PANTHEON_PY="$(cd "$SCRIPT_DIR/.." && pwd)"
PANTHEON_DIR="${1:-$(dirname "$PANTHEON_PY")/pantheon}"
PLAN="$(cat "$PANTHEON_PY/docs/design/repo-separation-plan.md")"
LOG_DIR="$PANTHEON_PY/.wave-logs"

mkdir -p "$LOG_DIR"

echo "=== Wave 2: Decouple pantheon-py from portable assets ==="
echo "  pantheon-py:  $PANTHEON_PY"
echo "  pantheon:     $PANTHEON_DIR"
echo "  logs:         $LOG_DIR"
echo ""

ALLOWED="Read,Write,Edit,Bash,Glob,Grep"

# ---------------------------------------------------------------------------
# Session E: Update config.py and pyproject.toml (Tasks 2.1, 2.2)
# ---------------------------------------------------------------------------
echo "[E] Starting: config.py, pyproject.toml"
cd "$PANTHEON_PY"
claude --worktree wave2-config -p "$(cat <<EOF
# Context

You are executing Wave 2, Tasks 2.1 and 2.2 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- pantheon-py repo: (you are in a worktree of it)
- pantheon repo (for reference only, do not modify): $PANTHEON_DIR

## Task 2.1: Update config.py

Read src/pantheon/config.py and refactor skills_dir() to resolve skills via this priority:
1. PANTHEON_AGENTS_DIR env var -- points to a pantheon repo checkout, look for .agents/skills/ under it
2. SKILLS_DIR env var -- legacy, direct path to a skills directory
3. .agents/ directory at repo root -- covers git submodule or symlink scenarios

Remove:
- _BUNDLED_SKILLS_DIR and all bundled-skills fallback logic
- Any imports or code paths that reference _bundled_skills

Update repo root detection so it does NOT depend on .agents/skills existing.
When no skills source is found, raise a clear error with a message like:
  "No skills directory found. Set PANTHEON_AGENTS_DIR to your pantheon repo checkout,
   or add a .agents/ submodule/symlink. See README.md for setup options."

Also apply the same pattern to any subagents directory resolution if it exists in config.

## Task 2.2: Update pyproject.toml

Remove the .agents/skills bundling:
- Delete the [tool.hatch.build.targets.wheel.force-include] section that maps
  ".agents/skills" to "pantheon/_bundled_skills"
- Remove "/.agents/skills/**" from [tool.hatch.build.targets.sdist] includes
- Remove "/AGENTS.md" from sdist includes (it now lives in the pantheon repo)

Commit your changes with a clear message. Do NOT push.
Report what changed.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave2-E.log" 2>&1 &
PID_E=$!

# ---------------------------------------------------------------------------
# Session F: Update Makefile, tasks.py, tests (Tasks 2.3, 2.4)
# ---------------------------------------------------------------------------
echo "[F] Starting: Makefile, tasks.py, tests"
cd "$PANTHEON_PY"
claude --worktree wave2-build -p "$(cat <<EOF
# Context

You are executing Wave 2, Tasks 2.3 and 2.4 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- pantheon-py repo: (you are in a worktree of it)
- pantheon repo (for reference only, do not modify): $PANTHEON_DIR

## Task 2.3: Update Makefile and tasks.py

Read the Makefile and tasks.py.

Changes needed:
- Remove .agents/skills/ from lint targets (ruff check, etc.) -- skills no longer live here
- Remove the validate-skills target entirely (validation now happens in the pantheon repo)
- Remove eval targets (eval, eval-skill, etc.) -- evals now live in the pantheon repo
- Remove any improve targets that reference evals
- Add a "setup-agents" target that prints instructions for how to configure the skills source:
  "Set PANTHEON_AGENTS_DIR, add a git submodule, or create a symlink. See README.md."
- Keep all runtime targets: install, dev, test, lint (for Python code), doctor, secret-scan, check, clean

Apply equivalent changes to tasks.py (the cross-platform task runner).

## Task 2.4: Update tests

Read the test files and audit for implicit dependencies on .agents/skills/ existing locally.

Key files to check:
- tests/test_skill.py -- likely depends on real SKILL.md files. Refactor to use mock/fixture
  skill directories with a minimal SKILL.md for testing. Create a conftest fixture that
  provides a tmp_path with a fake skills directory structure.
- tests/test_repo_scripts.py -- may reference skill_validate.py or other moved scripts.
  Update to skip or handle missing scripts gracefully.
- tests/test_claude_code_integration.py -- may reference .agents/ paths. Update.
- Any other test that reads from .agents/ -- check all test files.

Add a test for PANTHEON_AGENTS_DIR config resolution:
- Test that setting the env var resolves to the correct skills directory
- Test the error message when no source is configured

Commit your changes with a clear message. Do NOT push.
Report what changed.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave2-F.log" 2>&1 &
PID_F=$!

# ---------------------------------------------------------------------------
# Session G: Update observe, orchestrate, CLAUDE.md, scripts (Tasks 2.5, 2.6, 2.7)
# ---------------------------------------------------------------------------
echo "[G] Starting: observe, orchestrate, CLAUDE.md, scripts"
cd "$PANTHEON_PY"
claude --worktree wave2-misc -p "$(cat <<EOF
# Context

You are executing Wave 2, Tasks 2.5, 2.6, and 2.7 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- pantheon-py repo: (you are in a worktree of it)
- pantheon repo (for reference only, do not modify): $PANTHEON_DIR

## Task 2.5: Update observe.py and orchestrate.py

Read src/pantheon/observe.py:
- The ActivationTracker tracks SKILL.md reads. Ensure it works with any skills path,
  not just a hardcoded .agents/skills/ pattern. The path pattern matching should be
  flexible enough to handle skills discovered via PANTHEON_AGENTS_DIR.

Read src/pantheon/orchestrate.py:
- Update any hardcoded .agents/subagents/ references to use the config module's
  resolution logic instead. Subagents should be discovered the same way skills are --
  via PANTHEON_AGENTS_DIR, env var, or local .agents/.

## Task 2.6: Update pantheon-py CLAUDE.md

Read the current CLAUDE.md at the repo root.
Rewrite it to focus on the Python runtime project:

- Keep the project identity as "pantheon-py -- an agentic AI toolkit"
- Keep dev instructions: how to build, test, lint, run doctor
- Reference the pantheon repo for persona/skills: "Skills and agent definitions live in
  the pantheon repo. See docs for setup options."
- Remove the full Pantheon persona definition (Demeter identity, routing table, activation
  rule, protocol, rally, etc.) -- all of that now lives in pantheon/CLAUDE.md
- Keep it concise -- this is a Python project CLAUDE.md, not an agent persona definition

## Task 2.7: Update scripts and doctor.py

Read scripts/doctor.py:
- Add a health check for skills source: verify that one of the three resolution methods
  (PANTHEON_AGENTS_DIR, SKILLS_DIR, local .agents/) is configured and points to valid
  skill files. Report status clearly.
- Remove any references to scripts that moved to the pantheon repo
  (skill_validate.py, sync_subagents.py)

Read scripts/README.md:
- Update to reflect that skill_validate.py and sync_subagents.py have moved to the
  pantheon repo. Remove their entries or note the move.

Commit your changes with a clear message. Do NOT push.
Report what changed.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave2-G.log" 2>&1 &
PID_G=$!

# ---------------------------------------------------------------------------
# Wait for all sessions
# ---------------------------------------------------------------------------
echo ""
echo "All 3 sessions launched (each in its own worktree). Waiting for completion..."
echo "  Logs: $LOG_DIR/wave2-{E,F,G}.log"
echo ""

FAILED=0

wait $PID_E || { echo "[E] FAILED (exit $?)"; FAILED=1; }
echo "[E] Complete -- see $LOG_DIR/wave2-E.log"

wait $PID_F || { echo "[F] FAILED (exit $?)"; FAILED=1; }
echo "[F] Complete -- see $LOG_DIR/wave2-F.log"

wait $PID_G || { echo "[G] FAILED (exit $?)"; FAILED=1; }
echo "[G] Complete -- see $LOG_DIR/wave2-G.log"

echo ""

if [ $FAILED -ne 0 ]; then
    echo "=== Wave 2 FAILED -- check logs above ==="
    echo ""
    echo "Worktrees still exist for inspection. To list them:"
    echo "  cd $PANTHEON_PY && git worktree list"
    echo ""
    echo "To clean up after fixing:"
    echo "  git worktree remove .claude/worktrees/<name>"
    exit 1
fi

echo "=== Wave 2 sessions complete ==="
echo ""
echo "Each session committed to its own worktree branch."
echo "Next steps:"
echo "  1. Review each branch:"
echo "     git log --oneline wave2-config..HEAD  (Session E)"
echo "     git log --oneline wave2-build..HEAD   (Session F)"
echo "     git log --oneline wave2-misc..HEAD    (Session G)"
echo ""
echo "  2. Merge worktree branches into main:"
echo "     git merge worktree-wave2-config"
echo "     git merge worktree-wave2-build"
echo "     git merge worktree-wave2-misc"
echo ""
echo "  3. Or cherry-pick specific commits as needed."
echo ""
echo "  4. After merging and pushing, run ./scripts/wave3.sh"
