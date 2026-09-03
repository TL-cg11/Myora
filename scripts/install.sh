#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DB_NAME=${DB_NAME:-luck_db}
DB_USER=${DB_USER:-luck_user}
DB_PASSWORD=${DB_PASSWORD:-Luck1234!}
WAS_HOST=${WAS_HOST:-100.66.77.55}

sudo apt-get update
sudo apt-get install -y mariadb-server mariadb-client

sudo mkdir -p /etc/mysql/mariadb.conf.d
sudo rm -f /etc/mysql/conf.d/luck.cnf
sudo install -m 0644 mariadb.cnf /etc/mysql/mariadb.conf.d/99-luck.cnf

sudo systemctl enable mariadb
sudo systemctl restart mariadb

sudo mysql -uroot <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'$WAS_HOST' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'$WAS_HOST' IDENTIFIED BY '$DB_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`$DB_NAME\`.* TO '$DB_USER'@'$WAS_HOST';
CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

# sql/init 의 파일을 이름 순서대로 전부 적용한다. 타로 스키마와 기준 데이터가
# 02~04 에 있어서 01 만 적용하면 앱이 뜨지 않는다. 모두 재실행 안전하다.
for sql_file in sql/init/*.sql; do
  [ -f "$sql_file" ] || continue
  echo "applying $sql_file"
  sudo mysql -uroot "$DB_NAME" < "$sql_file"
done

DB_PASSWORD="$DB_PASSWORD" DB_USER="$DB_USER" DB_NAME="$DB_NAME" bash scripts/test.sh
