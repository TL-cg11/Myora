#!/usr/bin/env bash
# Docker 전용 MariaDB 초기화 스크립트.
#
# mariadb 공식 이미지는 최초 기동(빈 데이터 볼륨)에만 /docker-entrypoint-initdb.d 를 실행한다.
# 실행 권한이 있으면 실행하고 없으면 source 하는데, Windows bind mount 는 항상 실행 권한이
# 붙어 보이므로 두 경우 모두 동작하도록 entrypoint 헬퍼 대신 소켓으로 직접 접속한다.
#
# 하는 일은 서버용 scripts/install.sh + scripts/apply-security-monitoring-migration.sh 와 같다.
#   1. luck_db 생성, luck_user(DML 권한만) 생성
#   2. sql/init/*.sql 을 이름 순서대로 적용 (사주·타로·관상 스키마와 기준 데이터)
#   3. security_monitoring DB + 역할 + 서비스 계정 6종 + Grafana 읽기 전용 계정
#   4. 로컬 관제 API 테스트용 security_user 1명(ADMIN)
#
# 접속 허용 호스트는 Tailscale IP 대신 '%' 다. compose 네트워크 밖에서는 3306 을 열지 않는다.

luck_sql_dir=/luck-sql
luck_socket=${MARIADB_SOCKET:-/run/mysqld/mysqld.sock}

luck_fail() { echo "[init-luck] $*" >&2; exit 1; }

for luck_name in MARIADB_ROOT_PASSWORD LUCK_DB_NAME LUCK_DB_USER LUCK_DB_PASSWORD \
  SECURITY_MONITORING_MIGRATION_PASSWORD SECURITY_MONITORING_SINK_PASSWORD \
  SECURITY_MONITORING_API_PASSWORD SECURITY_MONITORING_READONLY_PASSWORD \
  SECURITY_MONITORING_NOTIFIER_PASSWORD SECURITY_MONITORING_RETENTION_PASSWORD \
  GRAFANA_SECURITY_DB_USER GRAFANA_SECURITY_DB_PASSWORD; do
  [ -n "${!luck_name:-}" ] || luck_fail "필수 환경변수가 없습니다: $luck_name"
done
luck_actor=${SECURITY_LOCAL_ACTOR_ID:-local-admin}

# 초기화 중 임시 서버는 소켓만 연다. root 비밀번호는 entrypoint 가 이미 설정한 상태다.
luck_sql() {
  mariadb --protocol=socket --socket="$luck_socket" -uroot --password="$MARIADB_ROOT_PASSWORD" \
    --default-character-set=utf8mb4 "$@" || luck_fail "SQL 실행 실패"
}
# 쉘 문자열을 SQL 리터럴에 직접 끼워 넣지 않고 base64 → FROM_BASE64 + QUOTE() 로 넘긴다.
luck_b64() { printf '%s' "$1" | base64 | tr -d '\n'; }

echo "[init-luck] 1/4 ${LUCK_DB_NAME} 와 ${LUCK_DB_USER} 준비"
luck_sql <<SQL
CREATE DATABASE IF NOT EXISTS \`${LUCK_DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @p = FROM_BASE64('$(luck_b64 "$LUCK_DB_PASSWORD")');
SET @s = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('${LUCK_DB_USER}'), '@', QUOTE('%'), ' IDENTIFIED BY ', QUOTE(@p));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @s = CONCAT('ALTER USER ', QUOTE('${LUCK_DB_USER}'), '@', QUOTE('%'), ' IDENTIFIED BY ', QUOTE(@p));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${LUCK_DB_NAME}\`.* TO '${LUCK_DB_USER}'@'%';
FLUSH PRIVILEGES;
SQL

echo "[init-luck] 2/4 sql/init/*.sql 적용"
for luck_file in "$luck_sql_dir"/init/*.sql; do
  [ -f "$luck_file" ] || continue
  echo "[init-luck]   applying $(basename "$luck_file")"
  luck_sql "$LUCK_DB_NAME" < "$luck_file"
done

echo "[init-luck] 3/4 security_monitoring 스키마·역할·계정"
luck_sql < "$luck_sql_dir/migrate/2026-09-07_security_monitoring.sql"
luck_sql < "$luck_sql_dir/migrate/2026-09-10_notification_discord.sql"

luck_account() {
  # $1 계정명, $2 역할, $3 비밀번호. 호스트는 '%'.
  luck_sql <<SQL
SET @p = FROM_BASE64('$(luck_b64 "$3")');
SET @s = CONCAT('CREATE USER IF NOT EXISTS ', QUOTE('$1'), '@', QUOTE('%'), ' IDENTIFIED BY ', QUOTE(@p));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @s = CONCAT('ALTER USER ', QUOTE('$1'), '@', QUOTE('%'), ' IDENTIFIED BY ', QUOTE(@p));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
GRANT $2 TO '$1'@'%';
SET DEFAULT ROLE $2 FOR '$1'@'%';
SQL
}
luck_account security_monitoring_migration security_monitoring_migration "$SECURITY_MONITORING_MIGRATION_PASSWORD"
luck_account security_monitoring_sink       security_monitoring_sink       "$SECURITY_MONITORING_SINK_PASSWORD"
luck_account security_monitoring_api        security_monitoring_api        "$SECURITY_MONITORING_API_PASSWORD"
luck_account security_monitoring_readonly   security_monitoring_readonly   "$SECURITY_MONITORING_READONLY_PASSWORD"
luck_account security_monitoring_notifier   security_monitoring_notifier   "$SECURITY_MONITORING_NOTIFIER_PASSWORD"
luck_account security_monitoring_retention  security_monitoring_retention  "$SECURITY_MONITORING_RETENTION_PASSWORD"
# Grafana 는 docs/grafana-security-monitoring.md 대로 읽기 전용 역할을 가진 전용 계정을 쓴다.
luck_account "$GRAFANA_SECURITY_DB_USER"    security_monitoring_readonly   "$GRAFANA_SECURITY_DB_PASSWORD"
luck_sql <<<'FLUSH PRIVILEGES;'

echo "[init-luck] 4/4 관제 API 로컬 사용자 ${luck_actor} (VIEWER/EDITOR/ADMIN)"
luck_sql security_monitoring <<SQL
INSERT IGNORE INTO security_user (actor_id, display_name, status)
VALUES ('${luck_actor}', 'Local security admin', 'ACTIVE');
INSERT IGNORE INTO security_user_role (user_id, role_id)
SELECT u.id, r.id FROM security_user u JOIN security_role r
WHERE u.actor_id = '${luck_actor}' AND r.role_code IN ('VIEWER','EDITOR','ADMIN');
SQL

echo "[init-luck] 완료"
