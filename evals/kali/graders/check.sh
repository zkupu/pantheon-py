#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="security-report.md not found"
c2_pass=false c2_msg="SQL injection not identified"
c3_pass=false c3_msg="Hardcoded secret not identified"
c4_pass=false c4_msg="eval() usage not identified"

if test -f security-report.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="security-report.md exists"
fi

report=$(cat security-report.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$report" | grep -q "sql.*inject\|injection\|sqli"; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="SQL injection vulnerability identified"
fi

if echo "$report" | grep -q "secret.key\|hardcod\|secret_key\|app\.secret"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Hardcoded secret identified"
fi

if echo "$report" | grep -q "eval("; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="eval() usage identified"
elif echo "$report" | grep -q "eval\|code.inject\|arbitrary.*exec\|remote.*code"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="eval/code execution risk identified"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"report-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"sql-injection\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"hardcoded-secret\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"eval-usage\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
