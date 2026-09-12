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
datasource automatically. It also provisions the security-event and consumer
dashboards plus lag, DLQ, and scrape-target alert rules. The provisioned Discord
contact point groups matching alerts for 30 seconds and repeats an unchanged
firing alert after four hours. Slack and SMTP are disabled.

## Service operations

```bash
sudo systemctl status loki prometheus grafana-server --no-pager
sudo systemctl restart loki prometheus grafana-server
sudo journalctl -u loki -u prometheus -u grafana-server -n 100 --no-pager
```

Do not add a public Nginx route or public firewall rule for ports 3100, 9090,
or 3000 without an explicit authentication and access-control design.
