#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="refactored.py not found"
c2_pass=false c2_msg="Cannot import refactored module"
c3_pass=false c3_msg="Still uses range(len(...))"
c4_pass=false c4_msg="No type hints found"

if test -f refactored.py; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="refactored.py exists"
fi

python3 -c "import refactored" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="Module imports successfully"
fi

if ! grep -q "range(len" refactored.py 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="No range(len(...)) anti-pattern"
fi

if grep -q "def.*->.*:" refactored.py 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Type hints present"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"imports\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"no-antipattern\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"type-hints\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
