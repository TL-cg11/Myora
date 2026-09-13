#!/usr/bin/env bash
set -euo pipefail

script="$(cd "$(dirname "$0")" && pwd)/run-part13-rollback-rehearsal.sh"
grep -q 'requires_execute' "$script"
grep -q 'mariadb-dump.*--no-data' "$script"
grep -q 'security_monitoring_rollback_test_' "$script"
grep -q 'DROP DATABASE IF EXISTS' "$script"
grep -q 'production_data_modified.*false' "$script"
grep -q -- '--cleanup-performance' "$script"
grep -q 'cleanup-part13-performance.sql' "$script"
grep -q 'events_after.*consumption_after' "$script"
echo 'Part 13 rollback rehearsal script verification passed.'
