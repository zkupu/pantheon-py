#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="design.md not found"
c2_pass=false c2_msg="No component/architecture section"
c3_pass=false c3_msg="No tradeoffs or alternatives"
c4_pass=false c4_msg="No risk section"

if test -f design.md; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="design.md exists"
fi

content=$(cat design.md 2>/dev/null | tr '[:upper:]' '[:lower:]')

if echo "$content" | grep -q "component\|architecture\|diagram\|service\|queue"; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Contains architecture/component discussion"
fi

if echo "$content" | grep -q "tradeoff\|trade-off\|alternative\|option\|versus\|vs\."; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Discusses tradeoffs or alternatives"
fi

if echo "$content" | grep -q "risk\|failure\|wrong\|concern\|caveat"; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Includes risk assessment"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"architecture\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"tradeoffs\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"risks\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
