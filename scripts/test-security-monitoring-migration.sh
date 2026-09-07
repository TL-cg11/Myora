#!/usr/bin/env bash
set -euo pipefail

# Read-only post-migration verification. Run on the MariaDB host as an admin.
expected_tables=(
  security_event security_event_detection security_event_action kafka_consumption
  consumer_failure notification_log security_user security_role security_user_role
)

for table_name in "${expected_tables[@]}"; do
  exists=$(sudo mysql -N -B -uroot -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'security_monitoring' AND table_name = '${table_name}';")
  if [[ "$exists" != '1' ]]; then
    echo "Missing table: security_monitoring.${table_name}" >&2
    exit 1
  fi
done

index_columns=$(sudo mysql -N -B -uroot -e "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = 'security_monitoring' AND table_name = 'kafka_consumption' AND index_name = 'uk_kafka_consumption_message';")
if [[ "$index_columns" != '4' ]]; then
  echo 'Missing composite idempotency index on kafka_consumption.' >&2
  exit 1
fi

role_mappings=$(sudo mysql -N -B -uroot -e "SELECT COUNT(*) FROM mysql.roles_mapping WHERE role IN ('security_monitoring_migration', 'security_monitoring_sink', 'security_monitoring_api', 'security_monitoring_readonly', 'security_monitoring_notifier', 'security_monitoring_retention');")
if [[ "$role_mappings" -lt '6' ]]; then
  echo 'Security-monitoring role mappings are incomplete.' >&2
  exit 1
fi

notifier_update=$(sudo mysql -N -B -uroot -e "SHOW GRANTS FOR security_monitoring_notifier;" | grep -c 'UPDATE.*notification_log' || true)
retention_delete=$(sudo mysql -N -B -uroot -e "SHOW GRANTS FOR security_monitoring_retention;" | grep -c 'DELETE.*security_event' || true)
if [[ "$notifier_update" -lt '1' || "$retention_delete" -lt '1' ]]; then
  echo 'Notifier or retention privileges are incomplete.' >&2
  exit 1
fi

echo 'security_monitoring migration verification passed.'
