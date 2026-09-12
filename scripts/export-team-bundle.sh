#!/usr/bin/env bash
# 이 PC 의 완성된 로컬 환경을 팀원에게 넘길 번들(zip)로 묶는다. 서버 SSH 접근이 없는 팀원용.
#   포함: .env (API 키·가명화 키·토큰), DB 덤프 2개, NER/문맥 모델 캐시(hf-cache 볼륨, 약 900MB)
#   bash scripts/export-team-bundle.sh [--no-models]
# 결과: .server/myora-team-bundle-<날짜>.zip  → 비밀이 들어 있으니 git 이 아니라 안전한 경로로 직접 전달한다.
set -euo pipefail
# Windows Git Bash 가 /경로 인자를 C:\Program Files\Git\... 로 바꾸는 것을 막는다 (docker 인자 보호).
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
WITH_MODELS=1; [ "${1:-}" = "--no-models" ] && WITH_MODELS=0
[ -f .env ] || { echo ".env 가 없습니다." >&2; exit 1; }
[ -f .server/mariadb/luck_db.sql ] || { echo ".server/mariadb/luck_db.sql 이 없습니다. scripts/dump-production-db.sh 를 먼저 실행하세요." >&2; exit 1; }
STAMP=$(date +%Y%m%d); WORK=.server/bundle-$STAMP; rm -rf "$WORK"; mkdir -p "$WORK/mariadb"
cp .env "$WORK/.env"
cp .server/mariadb/luck_db.sql .server/mariadb/security_monitoring.sql "$WORK/mariadb/" 2>/dev/null || cp .server/mariadb/luck_db.sql "$WORK/mariadb/"
if [ "$WITH_MODELS" = 1 ]; then
  VOLUME=$(docker compose config --format json | python -c "import sys,json; d=json.load(sys.stdin); print(d['volumes']['hf-cache'].get('name') or d['name']+'_hf-cache')")
  echo "모델 캐시 내보내기: 볼륨 $VOLUME → hf-cache.tar"
  docker run --rm -v "$VOLUME":/hf-cache:ro alpine sh -c 'tar -cf - -C /hf-cache hub' > "$WORK/hf-cache.tar"
fi
OUT=".server/myora-team-bundle-$STAMP.zip"; rm -f "$OUT"
( cd "$WORK" && python -c "
import zipfile, os
with zipfile.ZipFile('../$(basename "$OUT")', 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk('.'):
        for f in files: z.write(os.path.join(root, f))
" )
rm -rf "$WORK"
ls -la "$OUT"
echo "팀원: 레포 clone 후  bash scripts/import-team-bundle.sh <이 zip>"
