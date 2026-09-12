# Grafana security monitoring

## Data sources and dashboards

- `Prometheus` (`uid=prometheus`) supplies sink lag, throughput, latency, retry,
  failure, DLQ, and target-health metrics.
- `Loki` (`uid=loki`) supplies only streams labeled
  `pipeline=security-masked-logs,data_class=masked` to the masked-log panel.
- `Security Monitoring MariaDB` (`uid=security-monitoring-mysql`) uses the
  `security_monitoring_readonly` role through a dedicated `security_grafana`
  account. Its password is injected from `/etc/luck-observability.env` and is
  never stored in dashboard JSON.
- Provisioned dashboards are `Luck Security Events` and
  `Luck Security Consumers`. They are managed as code and are not UI-editable.

The long-unresolved table has a 24-hour visibility filter by default. Application
alert thresholds are risk-specific: CRITICAL 1 hour, HIGH 4 hours, MEDIUM 24
hours, and LOW 72 hours.

## Alert ownership boundary

Grafana Alerting owns infrastructure signals that are already Prometheus
metrics: consumer lag, DLQ occurrence, and unavailable scrape targets. Security
event notifications based on risk level, repeated behavior, or long-unresolved
state belong to the application notifier because they
require `event_id` deduplication and a durable `notification_log` transaction.
The `Luck Security Operations` contact point routes infrastructure alerts only
to Discord with 30-second grouping and a four-hour repeat interval. The webhook
is injected from `/etc/luck-observability.env`; Slack and SMTP are disabled.

## Server prerequisites

Create a dedicated MariaDB login and grant it only the existing read-only role:

```sql
CREATE USER IF NOT EXISTS 'security_grafana'@'100.%' IDENTIFIED BY '<strong-password>';
GRANT security_monitoring_readonly TO 'security_grafana'@'100.%';
SET DEFAULT ROLE security_monitoring_readonly FOR 'security_grafana'@'100.%';
```

Supply `GRAFANA_SECURITY_DB_HOST`, `GRAFANA_SECURITY_DB_PORT`,
`GRAFANA_SECURITY_DB_USER`, and `GRAFANA_SECURITY_DB_PASSWORD` when running the
observability installer. After Grafana restarts, confirm that both dashboards
load and that Alerting lists all five `luck-security-*` rules and the
`luck-security-discord` contact point receiver.
