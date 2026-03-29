#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="improved_errors.py not found"
c2_pass=false c2_msg="Still contains 'something went wrong'"
c3_pass=false c3_msg="Messages not descriptive"
c4_pass=false c4_msg="No actionable guidance in messages"

if test -f improved_errors.py; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="improved_errors.py exists"
fi

if ! grep -q "something went wrong" improved_errors.py 2>/dev/null; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Generic 'something went wrong' removed"
fi

avg_len=$(python3 - <<'PY'
import ast
from pathlib import Path

try:
    module = ast.parse(Path("improved_errors.py").read_text(encoding="utf-8"))
    messages: list[str] = []

    for node in module.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "ERRORS" for target in node.targets):
            continue

        for value in node.value.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                messages.append(value.value.strip())

    if messages:
        avg = sum(len(message) for message in messages) // len(messages)
        print(avg)
    else:
        print(0)
except Exception:
    print(0)
PY
)

if [ "${avg_len:-0}" -ge 30 ] 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Average message length ${avg_len} chars (descriptive)"
else
  c3_msg="Average message length ${avg_len:-0} chars (too short)"
fi

content=$(cat improved_errors.py 2>/dev/null | tr '[:upper:]' '[:lower:]')
if echo "$content" | grep -q "try\|check\|ensure\|please\|verify\|contact\|see\|support\|again\|correct\|make sure"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Messages include actionable guidance"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"no-generic\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"descriptive\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"actionable\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
