#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="counter.go not found"
c2_pass=false c2_msg="No sync primitive found"
c3_pass=false c3_msg="Missing required methods"
c4_pass=false c4_msg="Wrong package"

if test -f counter.go; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="counter.go exists"
fi

if grep -q "sync\.Mutex\|atomic\." counter.go 2>/dev/null; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Uses sync.Mutex or atomic"
fi

methods_found=0
for m in Increment Decrement Value Reset; do
  if grep -q "$m" counter.go 2>/dev/null; then
    methods_found=$((methods_found + 1))
  fi
done
if [ "$methods_found" -eq 4 ]; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="All 4 methods found"
fi

if grep -q "^package main" counter.go 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Uses package main"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"counter-go\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"sync-primitive\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"methods\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"package-main\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
