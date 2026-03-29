#!/bin/bash
passed=0
total=5
c1_pass=false c1_msg="analysis.md not found"
c2_pass=false c2_msg="No structured data extraction"
c3_pass=false c3_msg="No UI component identification"
c4_pass=false c4_msg="No alt text or description"
c5_pass=false c5_msg="No issues or recommendations"

if test -f analysis.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="analysis.md exists"
fi

content=$(cat analysis.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$content" | grep -qP '\$[\d,.]+[mk]?\b|revenue|orders|[\d]+%'; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Contains extracted data (numbers, revenue, percentages)"
fi

if echo "$content" | grep -q "card\|table\|button\|nav\|header\|grid\|layout\|component\|section"; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Identifies UI components"
fi

if echo "$content" | grep -q "alt text\|description\|screenshot\|caption\|visual\|image"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Provides alt text or visual description"
fi

if echo "$content" | grep -q "issue\|recommend\|improve\|suggest\|accessibility\|contrast\|concern"; then
  passed=$((passed + 1))
  c5_pass=true; c5_msg="Includes issues or recommendations"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"data-extraction\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"ui-components\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"alt-text\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"},{\"name\":\"recommendations\",\"passed\":$c5_pass,\"message\":\"$c5_msg\"}]}"
