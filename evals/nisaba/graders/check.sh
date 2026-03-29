#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="clean.md not found"
c2_pass=false c2_msg="Headings not properly spaced"
c3_pass=false c3_msg="List items not consistent"
c4_pass=false c4_msg="Code block has no language tag"

if test -f clean.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="clean.md exists"
fi

if grep -q "^# " clean.md 2>/dev/null && grep -q "^## " clean.md 2>/dev/null; then
  heading_count=$(grep -c "^##" clean.md 2>/dev/null)
  spaced_count=$(grep -B1 "^## " clean.md 2>/dev/null | grep -c "^$\|^--$" 2>/dev/null)
  if [ "$spaced_count" -ge 1 ] 2>/dev/null; then
    passed=$((passed + 1))
    c2_pass=true; c2_msg="Headings have proper spacing"
  fi
fi

list_count=$(grep -c "^- " clean.md 2>/dev/null)
if [ "${list_count:-0}" -ge 2 ] 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Found $list_count consistent list items"
fi

if grep -q '```python' clean.md 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Code block has python language tag"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"heading-spacing\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"list-consistency\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"code-lang\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
