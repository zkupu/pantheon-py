#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export PATH="$HOME/.local/share/fnm:$PATH"
eval "$(fnm env)" 2>/dev/null || true

if [ -f "$REPO_DIR/.env" ]; then
    set -a && source "$REPO_DIR/.env" && set +a
fi

export NIM_API_KEY="${INFERENCE_API_KEY:-${API_KEY:-}}"
export NIM_BASE_URL="${GATEWAY_URL:-}"
export NIM_MODEL="${NIM_MODEL:-azure/openai/gpt-4.1-mini}"

EVALS_DIR="$REPO_DIR/evals"
SKILLS=(themis aphrodite calliope eris freya pele seshat maat kali demeter)
RESULTS_FILE="$EVALS_DIR/bin/ultra-run-results.txt"

echo "=== Ultra Run — $(date) ===" > "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

for skill in "${SKILLS[@]}"; do
    echo "--- Running $skill ---"
    echo "--- $skill (started $(date +%H:%M:%S)) ---" >> "$RESULTS_FILE"
    cd "$EVALS_DIR/$skill"
    if output=$(skillgrade --smoke --provider=local --agent=nim 2>&1); then
        echo "$output"
        echo "$output" >> "$RESULTS_FILE"
        echo "--- $skill: EXIT 0 ---" >> "$RESULTS_FILE"
    else
        echo "$output"
        echo "$output" >> "$RESULTS_FILE"
        echo "--- $skill: EXIT $? ---" >> "$RESULTS_FILE"
    fi
    echo "" >> "$RESULTS_FILE"
done

echo "=== All done — $(date) ===" >> "$RESULTS_FILE"
echo "=== All done ==="
