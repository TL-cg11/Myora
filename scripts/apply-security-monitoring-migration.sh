#!/usr/bin/env bash
set -euo pipefail

# Run on the MariaDB host. The schema SQL never contains secrets; this bootstrap
# script reads service-account passwords only from the process environment.
cd "$(dirname "$0")/.."

required_vars=(
  SECURITY_MONITORING_MIGRATION_PASSWORD
  SECURITY_MONITORING_SINK_PASSWORD
  SECURITY_MONITORING_API_PASSWORD
  SECURITY_MONITORING_READONLY_PASSWORD
  SECURITY_MONITORING_NOTIFIER_PASSWORD
  SECURITY_MONITORING_RETENTION_PASSWORD
)
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required environment variable: ${var_name}" >&2
    exit 1
  fi
done

app_host=${SECURITY_MONITORING_APP_HOST:-100.66.77.55}
sink_host=${SECURITY_MONITORING_SINK_HOST:-$app_host}
api_host=${SECURITY_MONITORING_API_HOST:-$app_host}
readonly_host=${SECURITY_MONITORING_READONLY_HOST:-$app_host}
notifier_host=${SECURITY_MONITORING_NOTIFIER_HOST:-$app_host}
retention_host=${SECURITY_MONITORING_RETENTION_HOST:-$app_host}
for host_name in "$sink_host" "$api_host" "$readonly_host" "$notifier_host" "$retention_host"; do
  if [[ ! "$host_name" =~ ^[A-Za-z0-9._%:-]+$ ]]; then
    echo "Invalid MariaDB account host: ${host_name}" >&2
    exit 1
  fi
done

to_base64() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

migration_password_b64=$(to_base64 "$SECURITY_MONITORING_MIGRATION_PASSWORD")
sink_password_b64=$(to_base64 "$SECURITY_MONITORING_SINK_PASSWORD")
api_password_b64=$(to_base64 "$SECURITY_MONITORING_API_PASSWORD")
readonly_password_b64=$(to_base64 "$SECURITY_MONITORING_READONLY_PASSWORD")
notifier_password_b64=$(to_base64 "$SECURITY_MONITORING_NOTIFIER_PASSWORD")
retention_password_b64=$(to_base64 "$SECURITY_MONITORING_RETENTION_PASSWORD")
sink_host_b64=$(to_base64 "$sink_host")
api_host_b64=$(to_base64 "$api_host")
readonly_host_b64=$(to_base64 "$readonly_host")
notifier_host_b64=$(to_base64 "$notifier_host")
retention_host_b64=$(to_base64 "$retention_host")

sudo mysql -uroot < sql/migrate/2026-09-07_security_monitoring.sql

# Base64 keeps input out of a shell-built SQL literal; QUOTE() handles SQL
# metacharacters in the decoded passwords and host values.
sudo mysql -uroot <<SQL
SET @migration_password = FROM_BASE64('${migration_password_b64}');
SET @sink_password = FROM_BASE64('${sink_password_b64}');
SET @api_password = FROM_BASE64('${api_password_b64}');
SET @readonly_password = FROM_BASE64('${readonly_password_b64}');
SET @notifier_password = FROM_BASE64('${notifier_password_b64}');
SET @retention_password = FROM_BASE64('${retention_password_b64}');
SET @sink_host = FROM_BASE64('${sink_host_b64}');
SET @api_host = FROM_BASE64('${api_host_b64}');
SET @readonly_host = FROM_BASE64('${readonly_host_b64}');
SET @notifier_host = FROM_BASE64('${notifier_host_b64}');
SET @retention_host = FROM_BASE64('${retention_host_b64}');

SET @statement = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('security_monitoring_migration'), '@', QUOTE('localhost'), ' IDENTIFIED BY ', QUOTE(@migration_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('ALTER USER ', QUOTE('security_monitoring_migration'), '@', QUOTE('localhost'), ' IDENTIFIED BY ', QUOTE(@migration_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @statement = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('security_monitoring_sink'), '@', QUOTE(@sink_host), ' IDENTIFIED BY ', QUOTE(@sink_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('ALTER USER ', QUOTE('security_monitoring_sink'), '@', QUOTE(@sink_host), ' IDENTIFIED BY ', QUOTE(@sink_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @statement = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('security_monitoring_api'), '@', QUOTE(@api_host), ' IDENTIFIED BY ', QUOTE(@api_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('ALTER USER ', QUOTE('security_monitoring_api'), '@', QUOTE(@api_host), ' IDENTIFIED BY ', QUOTE(@api_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @statement = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('security_monitoring_readonly'), '@', QUOTE(@readonly_host), ' IDENTIFIED BY ', QUOTE(@readonly_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('ALTER USER ', QUOTE('security_monitoring_readonly'), '@', QUOTE(@readonly_host), ' IDENTIFIED BY ', QUOTE(@readonly_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @statement = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('security_monitoring_notifier'), '@', QUOTE(@notifier_host), ' IDENTIFIED BY ', QUOTE(@notifier_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('ALTER USER ', QUOTE('security_monitoring_notifier'), '@', QUOTE(@notifier_host), ' IDENTIFIED BY ', QUOTE(@notifier_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @statement = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('security_monitoring_retention'), '@', QUOTE(@retention_host), ' IDENTIFIED BY ', QUOTE(@retention_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('ALTER USER ', QUOTE('security_monitoring_retention'), '@', QUOTE(@retention_host), ' IDENTIFIED BY ', QUOTE(@retention_password));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;

GRANT security_monitoring_migration TO 'security_monitoring_migration'@'localhost';
SET DEFAULT ROLE security_monitoring_migration FOR 'security_monitoring_migration'@'localhost';

SET @statement = CONCAT('GRANT security_monitoring_sink TO ', QUOTE('security_monitoring_sink'), '@', QUOTE(@sink_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('SET DEFAULT ROLE security_monitoring_sink FOR ', QUOTE('security_monitoring_sink'), '@', QUOTE(@sink_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('GRANT security_monitoring_api TO ', QUOTE('security_monitoring_api'), '@', QUOTE(@api_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('SET DEFAULT ROLE security_monitoring_api FOR ', QUOTE('security_monitoring_api'), '@', QUOTE(@api_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('GRANT security_monitoring_readonly TO ', QUOTE('security_monitoring_readonly'), '@', QUOTE(@readonly_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('SET DEFAULT ROLE security_monitoring_readonly FOR ', QUOTE('security_monitoring_readonly'), '@', QUOTE(@readonly_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('GRANT security_monitoring_notifier TO ', QUOTE('security_monitoring_notifier'), '@', QUOTE(@notifier_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('SET DEFAULT ROLE security_monitoring_notifier FOR ', QUOTE('security_monitoring_notifier'), '@', QUOTE(@notifier_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('GRANT security_monitoring_retention TO ', QUOTE('security_monitoring_retention'), '@', QUOTE(@retention_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
SET @statement = CONCAT('SET DEFAULT ROLE security_monitoring_retention FOR ', QUOTE('security_monitoring_retention'), '@', QUOTE(@retention_host));
PREPARE statement FROM @statement; EXECUTE statement; DEALLOCATE PREPARE statement;
FLUSH PRIVILEGES;
SQL

echo 'security_monitoring schema and accounts are ready.'
