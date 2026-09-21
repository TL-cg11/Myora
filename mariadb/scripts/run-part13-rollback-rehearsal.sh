#!/usr/bin/env bash
set -euo pipefail

SOURCE_DB=security_monitoring
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
execute=false
cleanup_performance=false

for argument in "$@"; do
  case "$argument" in
    --execute) execute=true ;;
    --cleanup-performance) cleanup_performance=true ;;
    *)
      printf '{"status":"error","stage":"arguments","unknown":"%s"}\n' "$argument" >&2
      exit 2
      ;;
  esac
done

if [[ "$execute" != true ]]; then
  printf '{"status":"dry-run","part":"13-12","actions":["schema-only backup","temporary database restore","schema comparison","temporary database removal"],"cleanup_performance_requested":%s,"production_data_modified":false,"requires_execute":true}\n' "$cleanup_performance"
  exit 0
fi
if [[ ${EUID} -ne 0 ]]; then
  printf '%s\n' '{"status":"error","stage":"preflight","error":"run with sudo"}' >&2
  exit 2
fi

test_db="security_monitoring_rollback_test_${$}"
work_dir=$(mktemp -d)
dump_file="$work_dir/security-monitoring-schema.sql"

cleanup() {
  if [[ "$test_db" =~ ^security_monitoring_rollback_test_[0-9]+$ ]]; then
    mariadb -uroot -e "DROP DATABASE IF EXISTS \`$test_db\`;" >/dev/null
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT

source_count=$(mariadb -uroot -N -B -e \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$SOURCE_DB';")
if [[ "$source_count" -lt 9 ]]; then
  printf '%s\n' '{"status":"error","stage":"preflight","error":"security_monitoring schema is incomplete"}' >&2
  exit 2
fi

mariadb-dump -uroot --no-data --skip-comments --skip-add-locks "$SOURCE_DB" > "$dump_file"
dump_sha256=$(sha256sum "$dump_file" | awk '{print $1}')
mariadb -uroot -e "CREATE DATABASE \`$test_db\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mariadb -uroot "$test_db" < "$dump_file"

restored_count=$(mariadb -uroot -N -B -e \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$test_db';")
missing_required=$(mariadb -uroot -N -B -e \
  "SELECT COUNT(*) FROM (SELECT 'security_event' n UNION ALL SELECT 'security_event_detection' UNION ALL SELECT 'security_event_action' UNION ALL SELECT 'kafka_consumption' UNION ALL SELECT 'consumer_failure' UNION ALL SELECT 'notification_log') r LEFT JOIN information_schema.tables t ON t.table_schema='$test_db' AND t.table_name=r.n WHERE t.table_name IS NULL;")

status=ok
if [[ "$restored_count" != "$source_count" || "$missing_required" != 0 ]]; then
  status=failed
fi
printf '{"status":"%s","part":"13-12","source_tables":%s,"restored_tables":%s,"missing_required":%s,"dump_sha256":"%s","temporary_database":"removed-by-trap","production_data_modified":false}\n' \
  "$status" "$source_count" "$restored_count" "$missing_required" "$dump_sha256"
if [[ "$status" != ok ]]; then
  exit 1
fi

if [[ "$cleanup_performance" == true ]]; then
  events_before=$(mariadb -uroot -N -B "$SOURCE_DB" -e \
    "SELECT COUNT(*) FROM security_event WHERE event_id LIKE 'p13perf-%';")
  consumption_before=$(mariadb -uroot -N -B "$SOURCE_DB" -e \
    "SELECT COUNT(*) FROM kafka_consumption WHERE event_id LIKE 'p13perf-%';")
  mariadb -uroot < "$ROOT_DIR/scripts/cleanup-part13-performance.sql" >/dev/null
  events_after=$(mariadb -uroot -N -B "$SOURCE_DB" -e \
    "SELECT COUNT(*) FROM security_event WHERE event_id LIKE 'p13perf-%';")
  consumption_after=$(mariadb -uroot -N -B "$SOURCE_DB" -e \
    "SELECT COUNT(*) FROM kafka_consumption WHERE event_id LIKE 'p13perf-%';")
  printf '{"status":"%s","part":"13-14","action":"performance-fixture-cleanup","events_before":%s,"consumption_before":%s,"events_after":%s,"consumption_after":%s}\n' \
    "$([[ "$events_after" == 0 && "$consumption_after" == 0 ]] && printf ok || printf failed)" \
    "$events_before" "$consumption_before" "$events_after" "$consumption_after"
  [[ "$events_after" == 0 && "$consumption_after" == 0 ]]
fi
