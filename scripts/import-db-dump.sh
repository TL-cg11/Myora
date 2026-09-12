#!/usr/bin/env bash
# 기존 MariaDB 서버의 덤프를 로컬 Docker MariaDB 에 넣는다.
#
#   1) 서버에서 덤프 (한 번만):
#        ssh -t mariadb@100.104.124.29 "sudo mysqldump --single-transaction --databases luck_db security_monitoring > /tmp/luck-dump.sql"
#        scp mariadb@100.104.124.29:/tmp/luck-dump.sql ./luck-dump.sql
#   2) 이 스크립트:
#        bash scripts/import-db-dump.sh ./luck-dump.sql
#
# 덤프는 DROP TABLE + CREATE TABLE 을 포함하므로 서버 스키마로 통째로 바뀐다. 서버에 아직 적용되지
# 않았을 수 있는 이후 마이그레이션(16_ai_guardrail, notification_discord)을 import 뒤에 다시 적용한다
# (둘 다 IF NOT EXISTS / MODIFY 라 여러 번 실행해도 안전하다).
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP=${1:?"사용법: bash scripts/import-db-dump.sh <dump.sql>"}
[ -f "$DUMP" ] || { echo "덤프 파일이 없습니다: $DUMP" >&2; exit 1; }
[ -f .env ] || { echo ".env 가 없습니다. cp .env.example .env 를 먼저 실행하세요." >&2; exit 1; }
ROOT_PW=$(grep -E '^MARIADB_ROOT_PASSWORD=' .env | cut -d= -f2- | tr -d '\r')

if ! docker compose ps --status running mariadb --format '{{.Service}}' | grep -q mariadb; then
  echo "mariadb 컨테이너가 실행 중이 아닙니다. docker compose up -d mariadb" >&2
  exit 1
fi

sql() { docker compose exec -T mariadb mariadb -uroot -p"$ROOT_PW" --default-character-set=utf8mb4 "$@"; }

echo "[1/3] 덤프 적용: $DUMP ($(du -h "$DUMP" | cut -f1))"
# 앱이 붙어 있는 동안 DROP TABLE 이 잠기지 않도록 앱 컨테이너를 잠시 멈춘다.
docker compose stop was masking-adapter security-event-sink masked-log-sink >/dev/null
sql < "$DUMP"

echo "[2/3] 이후 마이그레이션 재적용"
sql luck_db < mariadb/sql/init/16_ai_guardrail.sql
sql < mariadb/sql/migrate/2026-09-10_notification_discord.sql
# 서버 덤프에 없을 수 있는 로컬 관제 계정(.env 의 SECURITY_LOCAL_ACTOR_ID)을 보장한다.
ACTOR=$(grep -E '^SECURITY_LOCAL_ACTOR_ID=' .env | cut -d= -f2- | tr -d '\r'); ACTOR=${ACTOR:-local-admin}
sql security_monitoring <<SQL
INSERT IGNORE INTO security_user (actor_id, display_name, status) VALUES ('${ACTOR}', 'Local security admin', 'ACTIVE');
INSERT IGNORE INTO security_user_role (user_id, role_id)
SELECT u.id, r.id FROM security_user u JOIN security_role r
WHERE u.actor_id = '${ACTOR}' AND r.role_code IN ('VIEWER','EDITOR','ADMIN');
SQL

echo "[3/3] 앱 재시작"
docker compose up -d was masking-adapter security-event-sink masked-log-sink >/dev/null
sql -e "SELECT 'app_user' t, COUNT(*) n FROM luck_db.app_user UNION ALL SELECT 'reading', COUNT(*) FROM luck_db.reading UNION ALL SELECT 'tarot_reading', COUNT(*) FROM luck_db.tarot_reading UNION ALL SELECT 'security_event', COUNT(*) FROM security_monitoring.security_event;"
echo "완료"
