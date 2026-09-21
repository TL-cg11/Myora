#!/usr/bin/env bash
# 회원을 관리자(role=admin)로 지정한다. 관리자는 /dashboard 와 /grafana/ 에 들어갈 수 있고 채팅 질문 한도가 늘어난다.
# 셀프서비스 승격 API 는 없으므로(mariadb/sql/migrate/2026-09-11_app_user_role.sql) DB 에서 직접 바꾼다.
#   bash scripts/make-admin.sh <username>          # 지정
#   bash scripts/make-admin.sh <username> --revoke # 해제
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
USERNAME=${1:?"사용법: bash scripts/make-admin.sh <username> [--revoke]"}
ROLE=admin; [ "${2:-}" = "--revoke" ] && ROLE=user
[[ "$USERNAME" =~ ^[A-Za-z0-9_]{4,40}$ ]] || { echo "username 형식이 아닙니다: $USERNAME" >&2; exit 1; }
ROOT_PW=$(grep -E '^MARIADB_ROOT_PASSWORD=' .env | cut -d= -f2- | tr -d '\r')
LUCK_DB=$(grep -E '^LUCK_DB_NAME=' .env | cut -d= -f2- | tr -d '\r'); LUCK_DB=${LUCK_DB:-luck_db}
docker compose exec -T mariadb mariadb -uroot -p"$ROOT_PW" "$LUCK_DB" -e \
  "UPDATE app_user SET role='$ROLE' WHERE username='$USERNAME'; SELECT username, role FROM app_user WHERE username='$USERNAME';"
echo "다시 로그인하면 적용된다."
