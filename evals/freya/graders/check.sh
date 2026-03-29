#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="plan.md not found"
c2_pass=false c2_msg="No subtasks found"
c3_pass=false c3_msg="No ordering or phases"
c4_pass=false c4_msg="No specialist assignment"

if test -f plan.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="plan.md exists"
fi

content=$(cat plan.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

subtask_count=$(echo "$content" | grep -c "task\|step\|phase\|subtask\|work item\|deliverable\|- \[\|^[0-9]\." 2>/dev/null)
if [ "$subtask_count" -ge 3 ] 2>/dev/null; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Contains $subtask_count subtask references"
fi

if echo "$content" | grep -q "phase\|order\|first\|then\|before\|after\|depend\|sequence\|priority\|block"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Includes ordering or phases"
fi

if echo "$content" | grep -q "backend\|frontend\|security\|test\|review\|specialist\|assign\|team\|engineer\|domain"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Routes work to specialists or domains"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"subtasks\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"ordering\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"routing\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
