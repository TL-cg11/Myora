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

## Rollback rehearsal

운영 데이터가 존재하는 `security_monitoring` database에는 destructive down migration을
실행하지 않는다. 아래 검증은 schema-only dump를 임시 database에 복원하고 필수 table과
전체 table 수를 비교한 뒤 임시 database를 제거한다. 원본 schema와 데이터는 변경하지 않는다.

```bash
sudo bash scripts/run-part13-rollback-rehearsal.sh
sudo bash scripts/run-part13-rollback-rehearsal.sh --execute
```

성능 검증 결과를 먼저 보관한 뒤 생성된 `p13perf-` 테스트 데이터까지 한 번에 정리하려면
두 번째 명령에 `--cleanup-performance`를 추가한다. 이 옵션은 정확히 `p13perf-` 접두사의
fixture만 삭제하며, 기본 dry-run에서는 삭제하지 않는다.

```bash
sudo bash scripts/run-part13-rollback-rehearsal.sh --execute --cleanup-performance
```

실제 복구는 배포 전 생성해 별도 보관한 전체 backup을 새 database에 먼저 복원하고 무결성
검증 후 접속 대상을 전환한다. backup 또는 복원 검증이 실패하면 기존 database를 유지한다.
