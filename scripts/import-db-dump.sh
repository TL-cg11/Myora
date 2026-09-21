#!/usr/bin/env bash
# 운영 MariaDB 덤프를 로컬 Docker MariaDB 에 넣는다.
#
#   bash scripts/dump-production-db.sh                      # 서버에서 덤프 (SSH 키 필요)
#   bash scripts/import-db-dump.sh .server/mariadb/luck_db.sql .server/mariadb/security_monitoring.sql
#
# 덤프는 DROP TABLE + CREATE TABLE 을 포함하므로 서버 스키마로 통째로 바뀐다. 서버에 아직 적용되지
# 않았을 수 있는 이후 마이그레이션을 import 뒤에 다시 적용한다(모두 IF NOT EXISTS / MODIFY 라 재실행 안전).
#
# 로컬에 넣지 않는 것:
#   - kafka_consumption 행: 서버 Kafka 의 offset 처리 이력이다. sink 는 (group, topic, partition, offset)
#     이 이미 있으면 메시지를 중복으로 보고 건너뛰므로 로컬 Kafka 에 그대로 넣으면 새 로그가 저장되지 않는다.
#   - notification_log 의 PENDING/SENDING 행은 SUPPRESSED 로 바꾼다. 그대로 두면 `--profile notify` 를
#     켜는 순간 서버에서 이미 처리 중이던 옛 알림이 팀 Discord 채널로 다시 나간다.
set -euo pipefail
# Windows Git Bash 가 /경로 인자를 C:\Program Files\Git\... 로 바꾸는 것을 막는다 (docker 인자 보호).
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

LUCK_DUMP=${1:?"사용법: bash scripts/import-db-dump.sh <luck_db.sql> [security_monitoring.sql]"}
SEC_DUMP=${2:-}
[ -f "$LUCK_DUMP" ] || { echo "덤프 파일이 없습니다: $LUCK_DUMP" >&2; exit 1; }
[ -z "$SEC_DUMP" ] || [ -f "$SEC_DUMP" ] || { echo "덤프 파일이 없습니다: $SEC_DUMP" >&2; exit 1; }
[ -f .env ] || { echo ".env 가 없습니다. cp .env.example .env 를 먼저 실행하세요." >&2; exit 1; }
ROOT_PW=$(grep -E '^MARIADB_ROOT_PASSWORD=' .env | cut -d= -f2- | tr -d '\r')
LUCK_DB=$(grep -E '^LUCK_DB_NAME=' .env | cut -d= -f2- | tr -d '\r'); LUCK_DB=${LUCK_DB:-luck_db}

if ! docker compose ps --status running mariadb --format '{{.Service}}' | grep -q mariadb; then
  echo "mariadb 컨테이너가 실행 중이 아닙니다. docker compose up -d mariadb" >&2
  exit 1
fi

sql() { docker compose exec -T mariadb mariadb -uroot -p"$ROOT_PW" --default-character-set=utf8mb4 "$@"; }
# 덤프에 USE/CREATE DATABASE 가 없으면(단일 DB 덤프) 대상 DB 를 지정해서 넣는다.
apply_dump() {
  local db=$1 file=$2
  if grep -qE '^USE `' "$file"; then sql < "$file"; else sql "$db" < "$file"; fi
}

echo "[1/4] 앱 컨테이너 일시 중지 (DROP TABLE 잠금 방지)"
docker compose stop was security-event-sink masked-log-sink security-notifier security-retention >/dev/null 2>&1 || true

echo "[2/4] luck_db 덤프 적용: $LUCK_DUMP ($(du -h "$LUCK_DUMP" | cut -f1))"
apply_dump "$LUCK_DB" "$LUCK_DUMP"

if [ -n "$SEC_DUMP" ]; then
  echo "[2/4] security_monitoring 덤프 적용: $SEC_DUMP ($(du -h "$SEC_DUMP" | cut -f1)) — kafka_consumption 행 제외"
  # INSERT 문은 여러 줄일 수 있으므로 문장이 끝나는 ';' 까지 통째로 건너뛴다.
  awk 'skip { if ($0 ~ /;[[:space:]]*$/) skip=0; next }
       /^INSERT INTO `kafka_consumption` / { if ($0 !~ /;[[:space:]]*$/) skip=1; next }
       { print }' "$SEC_DUMP" > "$SEC_DUMP.local.tmp"
  apply_dump security_monitoring "$SEC_DUMP.local.tmp"
  rm -f "$SEC_DUMP.local.tmp"
  sql security_monitoring -e "UPDATE notification_log SET status='SUPPRESSED', last_error='imported from production dump' WHERE status IN ('PENDING','SENDING');"
fi

echo "[3/4] 이후 마이그레이션 재적용"
sql "$LUCK_DB" < mariadb/sql/init/06_account.sql          # auth_ip_lockout 생성, 옛 계정 잠금 컬럼 제거 (재실행 안전)
sql "$LUCK_DB" < mariadb/sql/init/16_ai_guardrail.sql
sql "$LUCK_DB" < mariadb/sql/migrate/2026-09-11_app_user_role.sql
sql < mariadb/sql/migrate/2026-09-10_notification_discord.sql
sql < mariadb/sql/migrate/2026-09-16_notifier_detection_read.sql
# 서버 덤프에 없을 수 있는 로컬 관제 계정(.env 의 SECURITY_LOCAL_ACTOR_ID)을 보장한다.
ACTOR=$(grep -E '^SECURITY_LOCAL_ACTOR_ID=' .env | cut -d= -f2- | tr -d '\r'); ACTOR=${ACTOR:-local-admin}
sql security_monitoring <<SQL
INSERT IGNORE INTO security_user (actor_id, display_name, status) VALUES ('${ACTOR}', 'Local security admin', 'ACTIVE');
INSERT IGNORE INTO security_user_role (user_id, role_id)
SELECT u.id, r.id FROM security_user u JOIN security_role r
WHERE u.actor_id = '${ACTOR}' AND r.role_code IN ('VIEWER','EDITOR','ADMIN');
SQL

echo "[4/4] 앱 재시작"
docker compose up -d was security-event-sink masked-log-sink >/dev/null
sql -e "SELECT 'app_user' t, COUNT(*) n FROM ${LUCK_DB}.app_user UNION ALL SELECT 'reading', COUNT(*) FROM ${LUCK_DB}.reading UNION ALL SELECT 'tarot_reading', COUNT(*) FROM ${LUCK_DB}.tarot_reading UNION ALL SELECT 'tarot_chat_message', COUNT(*) FROM ${LUCK_DB}.tarot_chat_message UNION ALL SELECT 'security_event', COUNT(*) FROM security_monitoring.security_event UNION ALL SELECT 'security_user', COUNT(*) FROM security_monitoring.security_user;"
echo "완료"
