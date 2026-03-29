#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="analysis.md not found"
c2_pass=false c2_msg="No error code identified"
c3_pass=false c3_msg="No stack trace analysis"
c4_pass=false c4_msg="No actionable findings"

if test -f analysis.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="analysis.md exists"
fi

content=$(cat analysis.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$content" | grep -q "500\|internal server error\|error code"; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Identifies error code (500)"
fi

if echo "$content" | grep -q "typeerror\|userid\|auth\|middleware\|stack"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Analyzes stack trace content"
fi

if echo "$content" | grep -q "fix\|cause\|root cause\|undefined\|null check\|validation"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Provides actionable analysis"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"error-code\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"stack-trace\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"actionable\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
