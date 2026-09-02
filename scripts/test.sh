#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent --show-error http://127.0.0.1:8080/nginx-health
sudo tailscale serve status

STATUS_JSON=$(tailscale status --self --json 2>/dev/null || true)
DNS_NAME=$(printf '%s\n' "$STATUS_JSON" \
  | sed -n 's/.*"DNSName":[[:space:]]*"\([^"]*\)".*/\1/p' \
  | head -n 1 \
  | sed 's/\.$//')

if [ -z "$DNS_NAME" ]; then
  printf '%s\n' 'HTTPS DNS 이름을 자동으로 확인하지 못했습니다. 위 Serve 상태의 주소를 직접 확인하세요.' >&2
  exit 1
fi

curl --fail --silent --show-error "https://$DNS_NAME/nginx-health"
printf '\nHTTPS 확인 완료: https://%s/face\n' "$DNS_NAME"
