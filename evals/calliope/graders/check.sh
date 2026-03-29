#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="system_prompt.md not found"
c2_pass=false c2_msg="No role definition"
c3_pass=false c3_msg="No output format specified"
c4_pass=false c4_msg="No examples or patterns"

if test -f system_prompt.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="system_prompt.md exists"
fi

content=$(cat system_prompt.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$content" | grep -q "you are\|role\|act as\|your task\|you will\|assistant\|reviewer\|agent"; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Contains role definition"
fi

if echo "$content" | grep -q "format\|json\|structured\|output.*must\|respond with\|template\|section\|severity\|finding"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Specifies output format"
fi

if echo "$content" | grep -q "example\|pattern\|anti.pattern\|bare except\|eval\|sql.*inject\|injection\|xss\|security"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Includes examples or patterns to catch"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"role\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"format\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"examples\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
