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

The classified file is the live source of record. The IDS shipper sends one
normalized alert record per Suricata detection to Loki and does not publish Kafka
events. Grafana separately aggregates the four local Flood types over one minute
and sends one Discord notification per attack type and severity group instead of
notifying for every IDS entry.

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

`ids-events.jsonl` is rotated daily and keeps 30 compressed rotations. It contains
only the normalized IDS fields: source and destination addresses are reduced to a
network prefix, and the original EVE payload is not copied into this file. Raw EVE
alerts remain in Suricata's protected `/var/log/suricata/eve.json`.

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
