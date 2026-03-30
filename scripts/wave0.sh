#!/usr/bin/env bash
# Wave 0: Create the pantheon repo and establish the bridge
#
# Run interactively -- decisions may be needed.
# Prereq: none
# Output: pantheon repo on GitHub with skeleton structure,
#         bridge mechanism documented
#
# Usage: ./scripts/wave0.sh [pantheon-parent-dir]
#   pantheon-parent-dir: where to create the pantheon repo (default: sibling of pantheon-py)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PANTHEON_PY="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT_DIR="${1:-$(dirname "$PANTHEON_PY")}"
PANTHEON_DIR="$PARENT_DIR/pantheon"
PLAN="$PANTHEON_PY/docs/design/repo-separation-plan.md"

echo "=== Wave 0: Create pantheon repo ==="
echo "  pantheon-py: $PANTHEON_PY"
echo "  pantheon:    $PANTHEON_DIR"
echo ""

if [ -d "$PANTHEON_DIR" ]; then
    echo "ERROR: $PANTHEON_DIR already exists. Aborting."
    exit 1
fi

cat <<'PROMPT'
Starting interactive Claude Code session for Wave 0.

You will be asked to:
  1. Create the pantheon GitHub repo with skeleton structure
  2. Design and document the bridge mechanism (env var, submodule, symlink)

PROMPT

claude -p "$(cat <<EOF
Read the repo separation plan at: $PLAN

You are executing Wave 0 -- Tasks 0.1 and 0.2.

## Task 0.1: Create the pantheon repo

Create a new GitHub repo called "pantheon" under the same GitHub owner as pantheon-py.
Clone it to: $PANTHEON_DIR

Initialize with:
- MIT license (copy from $PANTHEON_PY/LICENSE)
- .gitignore for Python and common editor files
- README.md stub explaining this is the Pantheon portable agent framework
- Empty directory structure:
  .agents/skills/     (add .gitkeep)
  .agents/subagents/  (add .gitkeep)
  evals/              (add .gitkeep)
  scripts/            (add .gitkeep)
  docs/               (add .gitkeep)

Commit and push the skeleton.

## Task 0.2: Document the bridge mechanism

In the new pantheon repo, create docs/integration.md documenting how other projects
(like pantheon-py) consume this repo:

1. PANTHEON_AGENTS_DIR env var -- point at the repo root; the consumer reads .agents/skills/ and .agents/subagents/ from there
2. Git submodule -- add pantheon as a submodule at .agents/ in the consumer repo
3. Symlink -- symlink .agents/ in the consumer repo to the pantheon checkout's .agents/

Include setup commands for each method. This is external-only -- no bundling.

Commit and push when done. Then report what was created.
EOF
)" --allowedTools "Read,Write,Edit,Bash,Glob,Grep"

echo ""
echo "=== Wave 0 complete ==="
echo "pantheon repo: $PANTHEON_DIR"
echo ""
echo "Next: run ./scripts/wave1.sh and ./scripts/wave2.sh (can run in parallel)"
