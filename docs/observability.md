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
  bash scripts/observability-install.sh

sudo bash scripts/observability-test.sh
```

The installer pins Loki `3.0.0` and Prometheus `2.53.1` by default, creates
dedicated `loki` and `prometheus` system users, sets 30-day retention, and
installs Grafana from its official APT repository. The Grafana admin password
is stored only in `/etc/luck-observability.env` with mode `0600`.

| Service | Local health endpoint |
|---|---|
| Loki | `http://127.0.0.1:3100/ready` |
| Prometheus | `http://127.0.0.1:9090/-/ready` |
| Grafana | `http://127.0.0.1:3000/api/health` |

Grafana provisions the Prometheus and Loki datasources automatically. Part 6
will add private sink-consumer `/metrics` targets; dashboards and alert rules
remain deferred to Parts 8 through 10.

## Service operations

```bash
sudo systemctl status loki prometheus grafana-server --no-pager
sudo systemctl restart loki prometheus grafana-server
sudo journalctl -u loki -u prometheus -u grafana-server -n 100 --no-pager
```

Do not add a public Nginx route or public firewall rule for ports 3100, 9090,
or 3000 without an explicit authentication and access-control design.
