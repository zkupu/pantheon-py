#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="records.py not found"
c2_pass=false c2_msg="Cannot import parse_records"
c3_pass=false c3_msg="ruff check failed"
c4_pass=false c4_msg="Missing type hints"

if test -f records.py; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="records.py exists"
fi

python3 -c "from records import parse_records" 2>/dev/null
if [ $? -eq 0 ]; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="parse_records imports successfully"
fi

if python3 -m pip --version >/dev/null 2>&1; then
  python3 -m pip install -q --user ruff >/dev/null 2>&1 || python3 -m pip install -q ruff >/dev/null 2>&1
elif command -v pip >/dev/null 2>&1; then
  pip install -q --user ruff >/dev/null 2>&1 || pip install -q ruff >/dev/null 2>&1
fi

if python3 -m ruff check records.py >/dev/null 2>&1 || ruff check records.py >/dev/null 2>&1; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="ruff check passes"
fi

if grep -q "def parse_records.*->.*list\|def parse_records.*->.*List" records.py 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Type hints present"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"import-parse\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"ruff-clean\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"type-hints\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
