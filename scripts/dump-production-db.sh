#!/usr/bin/env bash
# 운영 3대 서버의 MariaDB 데이터를 앱 계정 권한만으로 덤프한다 (서버 root/sudo 불필요).
#   luck_db             : mariadb 서버 안에서 luck_user@127.0.0.1 로 mariadb-dump
#   security_monitoring : WAS 서버를 거치는 SSH 터널로 security_monitoring_api 계정 사용
#                         (계정이 WAS IP 에만 허용돼 있어서 WAS 를 경유한다)
# 비밀번호는 WAS 서버의 .env (DB_PASSWORD, SECURITY_DB_PASSWORD) 에서 읽는다.
#
#   bash scripts/dump-production-db.sh [출력 디렉터리]   (기본 .server/mariadb)
# 결과: <dir>/luck_db.sql, <dir>/security_monitoring.sql → scripts/import-db-dump.sh 로 넣는다.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-.server/mariadb}
WAS_HOST=${WAS_HOST:-was@100.66.77.55}
DB_HOST=${DB_HOST:-mariadb@100.104.124.29}
DB_IP=${DB_IP:-100.104.124.29}
mkdir -p "$OUT"

echo "[1/3] WAS 서버 .env 에서 DB 비밀번호 읽기"
ENV_TEXT=$(ssh -o BatchMode=yes "$WAS_HOST" 'cat ~/luck-was/.env')
getv() { printf '%s\n' "$ENV_TEXT" | grep -E "^$1=" | head -1 | cut -d= -f2- | tr -d "\r'\""; }
DBPW=$(getv DB_PASSWORD); SECPW=$(getv SECURITY_DB_PASSWORD)
[ -n "$DBPW" ] && [ -n "$SECPW" ] || { echo "DB_PASSWORD / SECURITY_DB_PASSWORD 를 읽지 못했습니다." >&2; exit 1; }
DUMP_OPTS="--single-transaction --skip-lock-tables --skip-triggers --no-tablespaces --default-character-set=utf8mb4 --hex-blob"

echo "[2/3] luck_db 덤프"
ssh -o BatchMode=yes "$DB_HOST" "MYSQL_PWD='$DBPW' mariadb-dump -h127.0.0.1 -uluck_user $DUMP_OPTS luck_db" > "$OUT/luck_db.sql"

echo "[3/3] security_monitoring 덤프 (WAS 경유 터널)"
ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -N -L 3308:"$DB_IP":3306 "$WAS_HOST" &
TUNNEL=$!
trap 'kill $TUNNEL 2>/dev/null || true' EXIT
sleep 3
docker run --rm --add-host=host.docker.internal:host-gateway -e MYSQL_PWD="$SECPW" mariadb:11.4 \
  mariadb-dump -hhost.docker.internal -P3308 -usecurity_monitoring_api $DUMP_OPTS security_monitoring \
  > "$OUT/security_monitoring.sql"

ls -la "$OUT"/luck_db.sql "$OUT"/security_monitoring.sql
echo "다음: bash scripts/import-db-dump.sh $OUT/luck_db.sql $OUT/security_monitoring.sql"
