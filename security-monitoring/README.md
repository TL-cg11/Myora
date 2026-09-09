# LUCK Suricata IDS pipeline

This directory adds a detection-only IDS pipeline beside Nginx. It does not edit
`nginx.conf`, its virtual host, Tailscale Serve, firewall rules, or packet routing.

```text
tailscale0 traffic -> Suricata -> /var/log/suricata/eve.json
                                      |
                                      v
                            IDS classifier
                                      |
                                      v
                /var/log/luck-security/ids-events.jsonl
```

Suricata uses its default `suricata-update` Emerging Threats Open community source,
plus four local detection-only threshold rules. Local alerts are classified as
`tcp_syn_flood`, `udp_flood`, `icmp_flood`, or `web_connection_flood`. Community
rules categorized as denial of service become `community_dos`; all other community
alerts remain `community_alert`.

The editable local rule source is deployed to
`/etc/suricata/luck-rules/luck-ddos.rules`. `suricata-update` merges it with ET Open
into `/var/lib/suricata/rules/suricata.rules`, which is the runtime rules file.

The ET Open feed and local rules are rebuilt daily by
`luck-suricata-update.timer`, followed by a live Suricata rule reload.

The classified file is the live source of record until the repository's shared Kafka
and Grafana services are ready. It can later be connected to the existing
`observability/` pipeline without changing Suricata or Nginx.

## Install

```bash
cd ~/luck-nginx
bash scripts/install-security-monitoring.sh
```

The installer prefers `tailscale0`. It installs only Suricata, the classifier, rule
updates, and log rotation; it does not install Docker, Kafka, Loki, or Grafana.

## Verify

```bash
cd ~/luck-nginx
bash scripts/test-security-monitoring.sh
sudo journalctl -u suricata -n 100 --no-pager
sudo journalctl -u luck-ids-classifier -n 100 --no-pager
sudo tail -f /var/log/luck-security/ids-events.jsonl
```

`ids-events.jsonl` is rotated daily, keeps 30 compressed rotations, and is suitable
as a future Kafka file-source input. `suricata_event` preserves the complete original
EVE alert while the top-level fields provide the normalized DDoS classification.

## EveBox web console

EveBox reads the raw EVE stream with its embedded SQLite store. Install it with:

```bash
bash scripts/install-evebox.sh
```

Nginx proxies only `/suricata/` to EveBox and redirects the exact `/suricata` path so
relative web assets load correctly. EveBox itself listens only on `127.0.0.1:5636`;
authentication remains enabled, and its first-start administrator password is recorded
in the `luck-evebox` service log. All existing application paths keep their original
proxy behavior.
