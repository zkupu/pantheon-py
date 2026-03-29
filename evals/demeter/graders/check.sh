#!/bin/bash
passed=0
total=4
c1_pass=false c1_msg="migration.sql not found"
c2_pass=false c2_msg="Missing CREATE TABLE users"
c3_pass=false c3_msg="Missing database host from config"
c4_pass=false c4_msg="Missing required columns"

if test -f migration.sql; then
  passed=$((passed + 1))
  c1_pass=true; c1_msg="migration.sql exists"
fi

if grep -qi "CREATE TABLE.*users" migration.sql 2>/dev/null; then
  passed=$((passed + 1))
  c2_pass=true; c2_msg="CREATE TABLE users found"
fi

if grep -q "db-primary.pantheon.internal" migration.sql 2>/dev/null; then
  passed=$((passed + 1))
  c3_pass=true; c3_msg="Database host referenced correctly"
fi

cols_found=0
grep -qi "id" migration.sql 2>/dev/null && cols_found=$((cols_found + 1))
grep -qi "email" migration.sql 2>/dev/null && cols_found=$((cols_found + 1))
grep -qi "created_at" migration.sql 2>/dev/null && cols_found=$((cols_found + 1))
if [ "$cols_found" -eq 3 ]; then
  passed=$((passed + 1))
  c4_pass=true; c4_msg="All 3 columns present (id, email, created_at)"
else
  c4_msg="Only $cols_found/3 columns found"
fi

score=$(awk "BEGIN {printf \"%.2f\", $passed/$total}")
echo "{\"score\":$score,\"details\":\"$passed/$total checks passed\",\"checks\":[{\"name\":\"file-exists\",\"passed\":$c1_pass,\"message\":\"$c1_msg\"},{\"name\":\"create-table\",\"passed\":$c2_pass,\"message\":\"$c2_msg\"},{\"name\":\"db-host\",\"passed\":$c3_pass,\"message\":\"$c3_msg\"},{\"name\":\"columns\",\"passed\":$c4_pass,\"message\":\"$c4_msg\"}]}"
