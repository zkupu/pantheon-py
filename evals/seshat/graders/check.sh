#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="analysis.md not found"
c2_pass=false c2_msg="No error rate mentioned"
c3_pass=false c3_msg="No latency analysis"
c4_pass=false c4_msg="No actionable findings"

if test -f analysis.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="analysis.md exists"
fi

content=$(cat analysis.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$content" | grep -q "500\|error.*rate\|failure\|5xx"; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Identifies 500 errors"
fi

if echo "$content" | grep -q "latency\|slow\|5023\|5[0-9]*ms\|timeout\|30001\|p99\|p95"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Analyzes latency"
fi

if echo "$content" | grep -q "recommend\|action\|investigate\|fix\|suggest\|finding"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Provides actionable findings"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"error-rate\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"latency\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"findings\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
