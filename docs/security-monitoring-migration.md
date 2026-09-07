# Security monitoring migration

`security_monitoring` is isolated from the existing `luck_db`. Apply this only on the MariaDB server, after the repository is updated, with administrative access:

```bash
cd ~/luck-mariadb
SECURITY_MONITORING_MIGRATION_PASSWORD='...' \
SECURITY_MONITORING_SINK_PASSWORD='...' \
SECURITY_MONITORING_API_PASSWORD='...' \
SECURITY_MONITORING_READONLY_PASSWORD='...' \
SECURITY_MONITORING_NOTIFIER_PASSWORD='...' \
SECURITY_MONITORING_RETENTION_PASSWORD='...' \
bash scripts/apply-security-monitoring-migration.sh

bash scripts/test-security-monitoring-migration.sh
```

No password is stored in Git. By default sink, API, readonly, notifier, and retention accounts are allowed only from the existing WAS IP (`100.66.77.55`). Override their host separately before running when deployment placement differs:

```bash
SECURITY_MONITORING_SINK_HOST='WAS-IP' \
SECURITY_MONITORING_API_HOST='WAS-IP' \
SECURITY_MONITORING_READONLY_HOST='GRAFANA-IP' \
SECURITY_MONITORING_NOTIFIER_HOST='WAS-IP' \
SECURITY_MONITORING_RETENTION_HOST='WORKER-IP' \
bash scripts/apply-security-monitoring-migration.sh
```

The migration account is intentionally restricted to `localhost`. Re-running the bootstrap is idempotent for tables, roles, permissions, and role seed data; it also rotates each supplied service-account password. It does not alter an already-existing incompatible table definition.
