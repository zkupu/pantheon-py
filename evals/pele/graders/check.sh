#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="Dockerfile not found"
c2_pass=false c2_msg="No FROM instruction"
c3_pass=false c3_msg="No EXPOSE instruction"
c4_pass=false c4_msg="No health check or CMD"

if test -f Dockerfile; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="Dockerfile exists"
fi

if grep -qi "^FROM" Dockerfile 2>/dev/null; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Has FROM instruction"
fi

if grep -qi "EXPOSE" Dockerfile 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Has EXPOSE instruction"
fi

if grep -qi "HEALTHCHECK\|CMD\|ENTRYPOINT" Dockerfile 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Has CMD/ENTRYPOINT/HEALTHCHECK"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"from\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"expose\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"cmd\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
