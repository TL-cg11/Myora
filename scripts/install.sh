#!/usr/bin/env bash
set -euo pipefail

if ! command -v mariadbd >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y mariadb-server mariadb-client
fi

sudo mkdir -p /etc/mysql/conf.d
sudo cp mariadb.cnf /etc/mysql/conf.d/luck.cnf

sudo mysql -uroot <<'SQL'
CREATE DATABASE IF NOT EXISTS luck_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'luck_user'@'127.0.0.1' IDENTIFIED BY 'Luck1234!';
GRANT ALL PRIVILEGES ON luck_db.* TO 'luck_user'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

if [ -f sql/init/01_init.sql ]; then
  sudo mysql -uroot luck_db < sql/init/01_init.sql
fi

sudo systemctl enable --now mariadb
sudo systemctl status mariadb --no-pager | head
