#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="challenge.md not found"
c2_pass=false c2_msg="No questions raised"
c3_pass=false c3_msg="No assumption challenged"
c4_pass=false c4_msg="No alternative suggested"

if test -f challenge.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="challenge.md exists"
fi

content=$(cat challenge.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

question_count=$(echo "$content" | grep -c "?" 2>/dev/null)
if [ "$question_count" -ge 2 ] 2>/dev/null; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Raises $question_count questions"
fi

if echo "$content" | grep -q "assum\|evidence\|proof\|data\|metric\|actually\|really\|why\|what if\|how do you know"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Challenges assumptions"
fi

if echo "$content" | grep -q "instead\|alternative\|modular\|modul\|simpler\|strangler\|incremental\|monolith\|consider"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Suggests alternatives"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"questions\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"assumptions\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"alternatives\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
