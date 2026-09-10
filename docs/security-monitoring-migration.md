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

Existing installations must apply the additive Discord channel migration once:

```bash
sudo mysql -uroot < sql/migrate/2026-09-10_notification_discord.sql
```

It preserves legacy `SLACK` and `EMAIL` history while allowing all new
notification rows to use `DISCORD`.

The verification script also confirms that `security_monitoring_api` can only
`SELECT` and `INSERT` rows in `security_event_action`; `UPDATE` and `DELETE` are
intentionally absent so audit history remains append-only even if an API bug is introduced.
The notifier role can `SELECT`, `INSERT`, and `UPDATE` only `notification_log`
and can only `SELECT` `security_event`; this permits unresolved-event scheduling
without allowing event or audit-history mutation.
