#!/usr/bin/env bash
# Wave 3: Validate and ship
#
# Runs validation across both repos, then cleans up.
# Prereq: Waves 1 and 2 complete and merged
#
# Usage: ./scripts/wave3.sh [pantheon-dir]
#   pantheon-dir: path to pantheon repo (default: sibling of pantheon-py)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PANTHEON_PY="$(cd "$SCRIPT_DIR/.." && pwd)"
PANTHEON_DIR="${1:-$(dirname "$PANTHEON_PY")/pantheon}"
PLAN="$(cat "$PANTHEON_PY/docs/design/repo-separation-plan.md")"
LOG_DIR="$PANTHEON_PY/.wave-logs"

mkdir -p "$LOG_DIR"

echo "=== Wave 3: Validate and ship ==="
echo "  pantheon-py:  $PANTHEON_PY"
echo "  pantheon:     $PANTHEON_DIR"
echo "  logs:         $LOG_DIR"
echo ""

if [ ! -d "$PANTHEON_DIR/.git" ]; then
    echo "ERROR: $PANTHEON_DIR is not a git repo."
    exit 1
fi

ALLOWED="Read,Write,Edit,Bash,Glob,Grep"

# ---------------------------------------------------------------------------
# Tasks 3.1 and 3.2 can run in parallel (different repos)
# ---------------------------------------------------------------------------

# Session H1: Validate pantheon repo standalone (Task 3.1)
echo "[H1] Starting: validate pantheon repo"
claude -p "$(cat <<EOF
# Context

You are executing Wave 3, Task 3.1 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directory

- pantheon repo: $PANTHEON_DIR

## Task 3.1: Validate pantheon repo standalone

cd to $PANTHEON_DIR and validate:

1. Verify all 24 skill directories exist under .agents/skills/, each with a SKILL.md
2. Verify all 10 subagent definitions exist under .agents/subagents/
3. Run: python scripts/skill_validate.py (if it exists) -- confirm all skills pass validation
4. Verify AGENTS.md exists and contains the routing table
5. Verify CLAUDE.md exists and contains the persona definition
6. Verify the docs/ directory contains: workflows.md, design/embedding-routing.md, research/instruction-decay.md
7. Verify the evals/ directory structure is intact (list eval dirs, spot-check a few eval.yaml files)
8. Check for any broken internal references (links to files that don't exist)

Report a clear pass/fail for each check. List any issues found.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave3-H1.log" 2>&1 &
PID_H1=$!

# Session H2: Validate pantheon-py with external skills (Task 3.2)
echo "[H2] Starting: validate pantheon-py with external skills"
claude -p "$(cat <<EOF
# Context

You are executing Wave 3, Task 3.2 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- pantheon-py repo: $PANTHEON_PY
- pantheon repo: $PANTHEON_DIR

## Task 3.2: Validate pantheon-py with external skills

cd to $PANTHEON_PY and validate:

1. Set PANTHEON_AGENTS_DIR=$PANTHEON_DIR and run: make check
   This should run lint + tests. All tests must pass.

2. Verify that config.py correctly resolves skills from PANTHEON_AGENTS_DIR:
   PANTHEON_AGENTS_DIR=$PANTHEON_DIR python -c "from pantheon.config import skills_dir; print(skills_dir())"

3. Unset PANTHEON_AGENTS_DIR and verify the error message is clear and helpful:
   python -c "from pantheon.config import skills_dir; print(skills_dir())" 2>&1 || true

4. Run: python scripts/doctor.py (or make doctor) -- verify it reports skills source status

5. Build the wheel and verify it does NOT contain _bundled_skills:
   python -m build --wheel
   unzip -l dist/*.whl | grep -c bundled || echo "No bundled skills (correct)"

6. Verify pyproject.toml no longer references .agents/

Report a clear pass/fail for each check. List any issues found.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave3-H2.log" 2>&1 &
PID_H2=$!

echo "Waiting for validation sessions..."
FAILED=0

wait $PID_H1 || { echo "[H1] FAILED (exit $?)"; FAILED=1; }
echo "[H1] Complete -- see $LOG_DIR/wave3-H1.log"

wait $PID_H2 || { echo "[H2] FAILED (exit $?)"; FAILED=1; }
echo "[H2] Complete -- see $LOG_DIR/wave3-H2.log"

if [ $FAILED -ne 0 ]; then
    echo ""
    echo "=== Validation FAILED -- check logs above ==="
    echo "Fix issues and re-run this script."
    exit 1
fi

echo ""
echo "--- Validation passed. Proceeding to remaining tasks... ---"
echo ""

# ---------------------------------------------------------------------------
# Tasks 3.3, 3.4, 3.5 run sequentially (they depend on validation passing)
# ---------------------------------------------------------------------------

# Session H3: Submodule test, READMEs, cleanup (Tasks 3.3, 3.4, 3.5)
echo "[H3] Starting: submodule test, READMEs, home cleanup"
claude -p "$(cat <<EOF
# Context

You are executing Wave 3, Tasks 3.3, 3.4, and 3.5 from the repo separation plan.
Validation (Tasks 3.1 and 3.2) has already passed.

<plan>
$PLAN
</plan>

## Working directories

- pantheon-py repo: $PANTHEON_PY
- pantheon repo: $PANTHEON_DIR
- Home directory: $HOME

## Task 3.3: Validate pantheon-py with submodule

In $PANTHEON_PY:
1. Add the pantheon repo as a git submodule at .agents/:
   git submodule add <pantheon-repo-url> .agents
2. Unset PANTHEON_AGENTS_DIR and run: make test
3. Verify skills are discovered via the submodule path
4. After testing, remove the submodule (this was just a validation test):
   git submodule deinit .agents
   git rm .agents
   git checkout -- .gitmodules 2>/dev/null || true
   rm -rf .git/modules/.agents 2>/dev/null || true

## Task 3.4: Update READMEs

Update $PANTHEON_DIR/README.md:
- Title: "The Pantheon -- Portable Agent Framework"
- Explain what it is: a collection of AI agent skills, personas, and routing definitions
- Explain it's harness-agnostic (works with Claude Code, Cursor, or any CLAUDE.md-compatible tool)
- Document the .agents/ directory structure
- Link to docs/integration.md for how to integrate with other projects
- Mention the eval suite

Update $PANTHEON_PY/README.md:
- Keep the existing runtime description
- Add a "Skills Setup" section explaining the three integration methods:
  1. PANTHEON_AGENTS_DIR env var
  2. Git submodule
  3. Symlink
- Link to the pantheon repo
- Remove any references to skills being bundled or included in this repo

Commit changes to each repo.

## Task 3.5: Clean up home directory

Check if $HOME/.agents/ still exists with skills and subagents.
If it contains the SAME files that are now in the pantheon repo:
- List what's there so the user can verify
- Create a symlink from $HOME/.agents to $PANTHEON_DIR/.agents
  (so the user's global CLAUDE.md still works)
- Print a message about what was done

Check if $HOME/CLAUDE.md references .agents/ paths.
If it does, note that it should be updated to point at the pantheon repo,
but do NOT modify it -- just report what needs to change and let the user decide.

Report all changes and recommendations.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave3-H3.log" 2>&1 &
PID_H3=$!

wait $PID_H3 || { echo "[H3] FAILED (exit $?)"; FAILED=1; }
echo "[H3] Complete -- see $LOG_DIR/wave3-H3.log"

echo ""
if [ $FAILED -ne 0 ]; then
    echo "=== Wave 3 FAILED -- check logs ==="
    exit 1
fi

echo "=== Wave 3 complete ==="
echo ""
echo "Repo separation is done. Summary:"
echo "  pantheon:    $PANTHEON_DIR (portable agent framework)"
echo "  pantheon-py: $PANTHEON_PY (Python runtime engine)"
echo ""
echo "Logs: $LOG_DIR/wave3-*.log"
echo ""
echo "Clean up wave logs when satisfied:"
echo "  rm -rf $LOG_DIR"
