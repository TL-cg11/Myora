# Server observability stack

Part 5-16 uses native Ubuntu systemd services, not Docker. Loki, Prometheus,
and Grafana bind only to `127.0.0.1`; the existing Nginx HTTPS configuration
does not publish their administration endpoints.

## Install and verify

Run on the Ubuntu 24.04 observability server after `git pull`:

```bash
cd ~/luck-nginx
sudo env GRAFANA_ADMIN_USER=admin \
  GRAFANA_ADMIN_PASSWORD='replace-with-a-strong-password' \
  GRAFANA_SECURITY_DB_HOST='100.104.124.29' \
  GRAFANA_SECURITY_DB_PORT='3306' \
  GRAFANA_SECURITY_DB_USER='security_grafana' \
  GRAFANA_SECURITY_DB_PASSWORD='replace-with-the-readonly-db-password' \
  GRAFANA_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/replace-me' \
  bash scripts/observability-install.sh

sudo bash scripts/observability-test.sh
```

Create the `security_grafana` account and grant it only the
`security_monitoring_readonly` role as described in
`docs/grafana-security-monitoring.md` before installation. The installer pins
Loki `3.0.0` and Prometheus `2.53.1` by default, creates
dedicated `loki` and `prometheus` system users, sets 30-day retention, and
installs Grafana from its official APT repository. The Grafana admin password
is stored only in `/etc/luck-observability.env` with mode `0600`.

| Service | Local health endpoint |
|---|---|
| Loki | `http://127.0.0.1:3100/ready` |
| Prometheus | `http://127.0.0.1:9090/-/ready` |
| Grafana | `http://127.0.0.1:3000/api/health` |

Grafana provisions Prometheus, Loki, and the read-only security MariaDB
datasource automatically. It also provisions the security-event, consumer,
Suricata IDS, and IDS shipper operation dashboards plus lag, DLQ, and
scrape-target alert rules. The provisioned Discord contact point groups matching
Grafana infrastructure alerts for 30 seconds and repeats an unchanged firing
alert after four hours. Slack and SMTP are disabled.

## Suricata IDS log shipper

The IDS classifier's normalized `/var/log/luck-security/ids-events.jsonl` is sent
to Loki by `luck-ids-loki-shipper`. It is a query-only observability stream: one
Suricata-confirmed alert becomes one Loki log entry. It neither writes Kafka nor
creates a Discord notification. The shipper saves records to a bounded filesystem
buffer before Loki submission; after a Loki outage it retries those records in
order. Records arriving after the configured buffer limit are counted as loss.

Install it on the Nginx/Suricata host only after the main observability stack is
ready:

```bash
cd ~/luck-nginx
sudo bash scripts/ids-loki-shipper-install.sh
sudo systemctl status luck-ids-loki-shipper --no-pager
curl --fail http://127.0.0.1:9110/metrics
```

Prometheus scrapes its loopback metrics through
`/etc/prometheus/ids-shipper-targets.yml`. The `Luck IDS Shipper Operations`
dashboard displays availability, last successful Loki send, buffer bytes and
ratio, retries, parse isolation, sent records, and unavoidable buffer-limit loss.

## Service operations

```bash
sudo systemctl status loki prometheus grafana-server --no-pager
sudo systemctl restart loki prometheus grafana-server
sudo journalctl -u loki -u prometheus -u grafana-server -n 100 --no-pager
```

Do not add a public Nginx route or public firewall rule for ports 3100, 9090,
or 3000 without an explicit authentication and access-control design.
