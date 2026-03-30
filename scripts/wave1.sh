#!/usr/bin/env bash
# Wave 1: Extract portable assets into the pantheon repo
#
# Launches 3 parallel Claude Code sessions (B, C, D) targeting the pantheon repo.
# Prereq: Wave 0 complete (pantheon repo exists)
#
# Usage: ./scripts/wave1.sh [pantheon-dir]
#   pantheon-dir: path to pantheon repo (default: sibling of pantheon-py)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PANTHEON_PY="$(cd "$SCRIPT_DIR/.." && pwd)"
PANTHEON_DIR="${1:-$(dirname "$PANTHEON_PY")/pantheon}"
PLAN="$(cat "$PANTHEON_PY/docs/design/repo-separation-plan.md")"
AGENTS_SRC="$HOME/.agents"
LOG_DIR="$PANTHEON_PY/.wave-logs"

mkdir -p "$LOG_DIR"

echo "=== Wave 1: Extract portable assets into pantheon ==="
echo "  pantheon-py:  $PANTHEON_PY"
echo "  pantheon:     $PANTHEON_DIR"
echo "  agents src:   $AGENTS_SRC"
echo "  logs:         $LOG_DIR"
echo ""

if [ ! -d "$PANTHEON_DIR/.git" ]; then
    echo "ERROR: $PANTHEON_DIR is not a git repo. Run wave0.sh first."
    exit 1
fi

ALLOWED="Read,Write,Edit,Bash,Glob,Grep"

# ---------------------------------------------------------------------------
# Session B: Move skills, subagents, AGENTS.md (Tasks 1.1, 1.2, 1.3)
# ---------------------------------------------------------------------------
echo "[B] Starting: skills, subagents, AGENTS.md"
claude -p "$(cat <<EOF
# Context

You are executing Wave 1, Tasks 1.1, 1.2, and 1.3 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- Source agents dir: $AGENTS_SRC
- Source pantheon-py repo: $PANTHEON_PY
- Target pantheon repo: $PANTHEON_DIR

## Task 1.1: Move skills

Copy all 24 skill directories from $AGENTS_SRC/skills/ into $PANTHEON_DIR/.agents/skills/.
Each skill directory contains a single SKILL.md file.
After copying, verify every SKILL.md exists and is non-empty.
Remove any .gitkeep placeholder files that are no longer needed.

## Task 1.2: Move subagents

Copy all 10 subagent definitions from $AGENTS_SRC/subagents/ into $PANTHEON_DIR/.agents/subagents/.
After copying, verify every subagent .md file exists and is non-empty.
Remove any .gitkeep placeholder files that are no longer needed.

## Task 1.3: Move AGENTS.md

Copy AGENTS.md from $PANTHEON_PY/ into $PANTHEON_DIR/.
Review it and strip any pantheon-py-specific content:
- Remove Python bootstrap commands (e.g., references to python scripts/doctor.py)
- Remove references to pyproject.toml, pip install, or Python-specific tooling
- Keep ALL routing tables, protocol, activation rules, specialist roster, dispatch patterns

Commit all changes to the pantheon repo with a clear commit message.
Do NOT push -- the orchestrator will push after all sessions complete.
Report what was done: file counts, any issues found.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave1-B.log" 2>&1 &
PID_B=$!

# ---------------------------------------------------------------------------
# Session C: Create portable CLAUDE.md, move evals (Tasks 1.4, 1.5)
# ---------------------------------------------------------------------------
echo "[C] Starting: portable CLAUDE.md, eval suite"
claude -p "$(cat <<EOF
# Context

You are executing Wave 1, Tasks 1.4 and 1.5 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- Source pantheon-py repo: $PANTHEON_PY
- Target pantheon repo: $PANTHEON_DIR

## Task 1.4: Create portable CLAUDE.md

Read the current CLAUDE.md from $PANTHEON_PY/CLAUDE.md.
Create a new CLAUDE.md in $PANTHEON_DIR/ that contains ONLY the portable persona layer:

Include:
- Demeter identity, behavioral rules, addressing conventions
- The full Specialist Domains routing table
- Disambiguation rules
- Parallel dispatch patterns
- Activation rule (complete -- this is critical)
- The 6-step protocol (Assess, Activate, Plan, Execute, Verify, Report)
- Skill discovery pointing to .agents/skills/<name>/SKILL.md
- Subagent dispatch patterns and the subagent roster table
- Rally protocol
- "When Things Go Wrong" section
- Re-anchor checkpoint, context decay warning, self-audit rules

Exclude:
- Any pantheon-py-specific bootstrap (python scripts/doctor.py, pip install, etc.)
- References to pyproject.toml or Python build tooling
- The "Bootstrap" section's project-specific line about "pantheon-py -- an agentic AI toolkit"

Replace the Bootstrap section with a generic one:
"On session start, BEFORE processing any user message, read the Specialist Domains table below.
It contains the specialist roster, routing table, and dispatch patterns. Without it, you cannot
classify or route."

## Task 1.5: Move eval suite

Copy the entire $PANTHEON_PY/evals/ directory into $PANTHEON_DIR/evals/.
This includes:
- _template/ directory
- bin/ directory (improve.py, run-remaining.sh, summarize.py, etc.)
- README.md
- All 22 skill eval directories (each with eval.yaml, fixtures/, graders/)

After copying, review scripts in evals/bin/ for any hardcoded paths that reference
pantheon-py-specific locations and update them to work standalone from the pantheon repo.

Remove any .gitkeep placeholder files that are no longer needed.

Commit all changes to the pantheon repo with a clear commit message.
Do NOT push -- the orchestrator will push after all sessions complete.
Report what was done.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave1-C.log" 2>&1 &
PID_C=$!

# ---------------------------------------------------------------------------
# Session D: Move scripts and docs (Tasks 1.6, 1.7)
# ---------------------------------------------------------------------------
echo "[D] Starting: scripts, docs"
claude -p "$(cat <<EOF
# Context

You are executing Wave 1, Tasks 1.6 and 1.7 from the repo separation plan.

<plan>
$PLAN
</plan>

## Working directories

- Source pantheon-py repo: $PANTHEON_PY
- Target pantheon repo: $PANTHEON_DIR

## Task 1.6: Move skill-related scripts

Copy these scripts from $PANTHEON_PY/scripts/ to $PANTHEON_DIR/scripts/:
- skill_validate.py -- validates SKILL.md format
- sync_subagents.py -- syncs subagent definitions

Review each script for hardcoded paths that reference pantheon-py-specific locations.
Update paths to work from the pantheon repo root (e.g., look for .agents/skills/ relative
to the script's own repo, not a hardcoded external path).

Do NOT copy these (they stay in pantheon-py):
- doctor.py, install.py, secret_scan.py, thread_common.py

Remove any .gitkeep placeholder files that are no longer needed.

## Task 1.7: Move persona/skill documentation

Copy these docs from $PANTHEON_PY/docs/ to $PANTHEON_DIR/docs/:
- workflows.md (workflow templates that invoke Pantheon specialists)
- design/embedding-routing.md (routing model design)
- research/instruction-decay.md (instruction/prompt behavior research)

Create the subdirectory structure as needed (docs/design/, docs/research/).

These docs stay in pantheon-py (do NOT copy):
- cli-reference.md
- configuration-reference.md
- runtime-reference.md
- troubleshooting.md
- design/async-support.md
- design/sqlite-memory.md
- design/repo-separation-plan.md

Commit all changes to the pantheon repo with a clear commit message.
Do NOT push -- the orchestrator will push after all sessions complete.
Report what was done.
EOF
)" --allowedTools "$ALLOWED" \
   > "$LOG_DIR/wave1-D.log" 2>&1 &
PID_D=$!

# ---------------------------------------------------------------------------
# Wait for all sessions
# ---------------------------------------------------------------------------
echo ""
echo "All 3 sessions launched. Waiting for completion..."
echo "  Logs: $LOG_DIR/wave1-{B,C,D}.log"
echo ""

FAILED=0

wait $PID_B || { echo "[B] FAILED (exit $?)"; FAILED=1; }
echo "[B] Complete -- see $LOG_DIR/wave1-B.log"

wait $PID_C || { echo "[C] FAILED (exit $?)"; FAILED=1; }
echo "[C] Complete -- see $LOG_DIR/wave1-C.log"

wait $PID_D || { echo "[D] FAILED (exit $?)"; FAILED=1; }
echo "[D] Complete -- see $LOG_DIR/wave1-D.log"

echo ""

if [ $FAILED -ne 0 ]; then
    echo "=== Wave 1 FAILED -- check logs above ==="
    exit 1
fi

# Push the pantheon repo (all sessions committed locally)
echo "Pushing pantheon repo..."
cd "$PANTHEON_DIR" && git push
echo ""
echo "=== Wave 1 complete ==="
echo "Next: run ./scripts/wave3.sh (after wave2.sh is also complete)"
