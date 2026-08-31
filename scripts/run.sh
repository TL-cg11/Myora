#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  bash scripts/install.sh
fi

. .venv/bin/activate
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
