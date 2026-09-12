#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR=/opt/luck-security-monitoring

sudo suricata -T -c /etc/suricata/suricata.yaml
sudo systemctl is-active --quiet suricata
sudo systemctl is-active --quiet luck-suricata-update.timer
sudo systemctl is-active --quiet luck-ids-classifier
sudo systemctl is-active --quiet nginx
sudo nginx -t

SAMPLE='{"timestamp":"2026-09-09T00:00:00Z","event_type":"alert","src_ip":"198.51.100.10","dest_ip":"100.117.253.9","proto":"TCP","alert":{"signature":"LUCK DDOS TCP SYN flood","signature_id":1000001,"category":"Attempted Denial of Service","severity":2}}'
printf '%s\n' "$SAMPLE" \
  | python3 /usr/local/lib/luck-security/ids_classifier.py --classify-stdin \
  | jq -e '.attack_type == "tcp_syn_flood" and .is_ddos == true' >/dev/null

sudo test -f /var/log/suricata/eve.json
sudo test -f /var/log/luck-security/ids-events.jsonl

printf '%s\n' 'Security monitoring validation passed; Nginx remains active.'
