#!/usr/bin/env bash
set -euo pipefail

DB_NAME=${DB_NAME:-luck_db}
DB_USER=${DB_USER:-luck_user}
DB_PASSWORD=${DB_PASSWORD:-Luck1234!}

MYSQL_PWD="$DB_PASSWORD" mysql \
  --protocol=TCP \
  --host=127.0.0.1 \
  --user="$DB_USER" \
  --database="$DB_NAME" \
  --execute="SELECT status, checked_at FROM health_check ORDER BY id DESC LIMIT 1;"
