#!/usr/bin/env bash
set -euo pipefail

fixture_sql="$(cd "$(dirname "$0")" && pwd)/part13-retention-fixture.sql"
required_tables=(
  security_event security_event_detection security_event_action kafka_consumption
  consumer_failure notification_log
)

for table_name in "${required_tables[@]}"; do
  grep -q "INSERT INTO ${table_name}" "$fixture_sql"
done
grep -q 'INTERVAL 400 DAY' "$fixture_sql"
grep -q 'INTERVAL 20 DAY' "$fixture_sql"
grep -q 'INTERVAL 100 DAY' "$fixture_sql"

echo 'Part 13 retention fixture SQL verification passed.'
