#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="ci.yml not found"
c2_pass=false c2_msg="Not valid YAML structure"
c3_pass=false c3_msg="No pytest step"
c4_pass=false c4_msg="No lint step"

ci_file=""
for f in .github/workflows/ci.yml .github/workflows/ci.yaml ci.yml ci.yaml; do
  if test -f "$f"; then ci_file="$f"; break; fi
done

if [ -n "$ci_file" ]; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="$ci_file exists"
fi

if [ -n "$ci_file" ]; then
  python3 -c "import yaml; yaml.safe_load(open('$ci_file'))" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    passed=$((passed + 1))
    c2_pass=true; c2_msg="Valid YAML"
  else
    if grep -q "name:" "$ci_file" 2>/dev/null && grep -q "on:" "$ci_file" 2>/dev/null && grep -q "jobs:" "$ci_file" 2>/dev/null; then
      passed=$((passed + 1))
      c2_pass=true; c2_msg="Contains valid workflow structure (name, on, jobs)"
    fi
  fi
fi

if [ -n "$ci_file" ] && grep -qi "pytest\|test" "$ci_file" 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Contains test step"
fi

if [ -n "$ci_file" ] && grep -qi "ruff\|lint\|mypy" "$ci_file" 2>/dev/null; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="Contains lint step"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"valid-yaml\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"test-step\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"lint-step\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
