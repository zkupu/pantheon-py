#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="test_calculator.py not found"
c2_pass=false c2_msg="pytest did not pass"
c3_pass=false c3_msg="Fewer than 8 test functions"
c4_pass=false c4_msg="No division-by-zero test found"

if test -f test_calculator.py; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="test_calculator.py exists"
fi

if python3 -m pip --version >/dev/null 2>&1; then
  python3 -m pip install -q --user pytest >/dev/null 2>&1 || python3 -m pip install -q pytest >/dev/null 2>&1
elif command -v pip >/dev/null 2>&1; then
  pip install -q --user pytest >/dev/null 2>&1 || pip install -q pytest >/dev/null 2>&1
fi

pytest_output=$(python3 -m pytest --rootdir=. -c /dev/null test_calculator.py -v 2>&1)
pytest_status=$?
if [ "$pytest_status" -eq 0 ]; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="All tests pass"
else
  c2_msg="Tests failed: $(echo "$pytest_output" | tail -1)"
fi

test_count=$(grep -c "def test_" test_calculator.py 2>/dev/null)
if [ "$test_count" -ge 8 ] 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Found $test_count test functions (>= 8)"
else
  c3_msg="Found ${test_count:-0} test functions (need >= 8)"
fi

if grep -qi "zero\|ZeroDivision\|divide.*0\|division_by_zero" test_calculator.py 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Division-by-zero test found"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"tests-pass\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"test-count\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"division-zero\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
