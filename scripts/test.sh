#!/usr/bin/env bash
set -euo pipefail

mysql --protocol=TCP -h 127.0.0.1 -u luck_user -pLuck1234! -e "SHOW DATABASES; USE luck_db; SELECT * FROM health_check LIMIT 5;"
