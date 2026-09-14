# Grafana security monitoring

## Data sources and dashboards

- `Prometheus` (`uid=prometheus`) supplies sink lag, throughput, latency, retry,
  failure, DLQ, and target-health metrics.
- `Loki` (`uid=loki`) supplies masked application-log streams and the separate
  `job=luck-suricata-ids` IDS stream. IDS JSON fields include only normalized
  detection data; individual IP addresses and raw EVE payloads are excluded.
- `Security Monitoring MariaDB` (`uid=security-monitoring-mysql`) uses the
  `security_monitoring_readonly` role through a dedicated `security_grafana`
  account. Its password is injected from `/etc/luck-observability.env` and is
  never stored in dashboard JSON.
- Provisioned dashboards are `Luck Security Events`, `Luck Security Consumers`,
  `Luck Suricata IDS`, and `Luck IDS Shipper Operations`. They are managed as
  code and are not UI-editable.
- The site administrator page exposes three tabs in order: `Luck Security Events`,
  `Luck Security Consumers`, and `Luck Suricata IDS`. Application security events
  remain MariaDB-backed in the first tab. All Suricata flood counts, severity
  graphs, and recent alert logs remain in the third tab so raw IDS alert volume is
  not compared directly with application-event counts. Shipper health remains on
  the operations dashboard.
- The Suricata IDS tab displays only the four local Flood types. Its attack and
  severity legends remain visible as zero-valued series during quiet periods;
  generic `community_alert` records stay in Loki but are excluded from this view.
- The masked-log panel renders only `masked_message`; the complete validated JSON
  remains stored in Loki for controlled troubleshooting.

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
Each sink exposes zero-valued DLQ counters for every terminal failure stage at
startup. The DLQ rule combines the five-minute counter increase with new-series
detection so that the first DLQ message after process startup is not missed.

Suricata IDS entries are intentionally query-only. A Suricata rule has already
performed the flood threshold decision, so Grafana displays its normalized alert
without re-aggregating it and without emitting a per-entry Discord message. The
separate IDS shipper operations dashboard is where buffer capacity, retries,
parse isolation, and loss must be checked.

## Administrator dashboard

The public site exposes the monitoring view only at `/dashboard`; it embeds
Grafana through the same-origin `/grafana/` reverse proxy. The Nginx
`auth_request` calls WAS `/api/auth/admin-check`, which accepts the existing
one-hour HttpOnly session cookie (or a valid Bearer session) and requires
`app_user.role = 'admin'`. Nginx copies the returned identity to Grafana's
auth-proxy header, and clears client-provided cookies, Bearer credentials, and
identity headers before proxying to Grafana.

Run the one-batch server application from the Nginx host after the normal
Grafana installer environment variables are available:

```bash
cd ~/luck-nginx
bash scripts/run-part14-dashboard.sh --dry-run
sudo bash scripts/run-part14-dashboard.sh --execute
```

On the MariaDB host, assign an already-registered account separately with the
existing role migration comment as the template; the Nginx script never opens a
database connection. Verify that `ss -ltn` reports Grafana only at `127.0.0.1:3000`, then
check unauthenticated and ordinary-user `/dashboard` and `/grafana/` requests
are rejected, while an administrator sees both embedded dashboards. Grafana
starts with no anonymous access or native login form; SSH-tunnel access to
port 3000 is intentionally outside the supported browser path.

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
