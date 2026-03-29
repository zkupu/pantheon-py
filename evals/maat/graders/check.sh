#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="assessment.md not found"
c2_pass=false c2_msg="No clear recommendation"
c3_pass=false c3_msg="No discussion of precedent/culture risk"
c4_pass=false c4_msg="No alternative proposed"

if test -f assessment.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="assessment.md exists"
fi

content=$(cat assessment.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$content" | grep -q "recommend\|verdict\|decision\|conclusion\|approve\|reject"; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Contains a clear recommendation"
fi

if echo "$content" | grep -q "precedent\|culture\|norm\|standard\|slippery\|debt\|discipline"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Addresses precedent or culture risk"
fi

if echo "$content" | grep -q "alternative\|instead\|compromise\|middle\|partial\|minimal"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Proposes an alternative or compromise"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"recommendation\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"culture-risk\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"alternative\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
