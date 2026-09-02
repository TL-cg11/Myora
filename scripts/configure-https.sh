#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL=${BACKEND_URL:-http://127.0.0.1:8080}

if ! command -v tailscale >/dev/null 2>&1; then
  printf '%s\n' \
    '오류: Tailscale이 설치되어 있지 않습니다.' \
    '먼저 이 서버를 tailnet에 연결한 뒤 다시 실행하세요.' >&2
  exit 1
fi

if ! tailscale ip -4 >/dev/null 2>&1; then
  printf '%s\n' \
    '오류: 이 서버가 Tailscale에 연결되어 있지 않습니다.' \
    '`sudo tailscale up`으로 연결한 뒤 다시 실행하세요.' >&2
  exit 1
fi

if ! sudo tailscale serve --bg --https=443 "$BACKEND_URL"; then
  printf '%s\n' \
    'HTTPS 구성을 완료하지 못했습니다.' \
    'Tailscale 관리자 콘솔의 DNS 페이지에서 MagicDNS와 HTTPS Certificates를 활성화한 뒤 다시 실행하세요:' \
    'https://login.tailscale.com/admin/dns' >&2
  exit 1
fi

printf '\nHTTPS 구성이 완료되었습니다. 아래 Available within your tailnet 주소로 접속하세요.\n'
sudo tailscale serve status
