#!/usr/bin/env bash
# 팀원용: export-team-bundle.sh 로 만든 zip 하나로 .env·운영 데이터·모델 캐시를 한 번에 적용한다.
#   git clone https://github.com/TL-cg11/Myora.git && cd Myora
#   bash scripts/import-team-bundle.sh ~/Downloads/myora-team-bundle-20260912.zip
# Windows 는 Git Bash 에서 실행한다 (Git for Windows 에 포함).
set -euo pipefail
# Windows Git Bash 가 /경로 인자를 C:\Program Files\Git\... 로 바꾸는 것을 막는다 (docker 인자 보호).
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
ZIP=${1:?"사용법: bash scripts/import-team-bundle.sh <myora-team-bundle-*.zip>"}
[ -f "$ZIP" ] || { echo "파일이 없습니다: $ZIP" >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker Desktop 을 먼저 설치하고 실행하세요." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker 가 실행 중이 아닙니다. Docker Desktop 을 켜세요." >&2; exit 1; }

WORK=.server/bundle-import; rm -rf "$WORK"; mkdir -p "$WORK"
python -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP" "$WORK"

echo "[1/4] .env 적용"
if [ -f .env ]; then cp .env ".env.backup-$(date +%Y%m%d%H%M%S)"; echo "      기존 .env 는 백업했습니다."; fi
cp "$WORK/.env" .env
# 번들의 .env 는 NER 이미지를 켜 둔 상태다. 모델이 번들에 없으면 정규식 전용으로 내린다.
if [ ! -f "$WORK/hf-cache.tar" ]; then
  sed -i.bak -E 's/^ADAPTER_BUILD_TARGET=.*/ADAPTER_BUILD_TARGET=runtime/; s/^DETECTOR_NER_ENABLED=.*/DETECTOR_NER_ENABLED=false/; s/^DETECTOR_PII_CONTEXT_ENABLED=.*/DETECTOR_PII_CONTEXT_ENABLED=false/' .env && rm -f .env.bak
  echo "      모델 캐시가 번들에 없어 NER/문맥 재검증은 끈 상태로 둡니다."
fi

if [ -f "$WORK/hf-cache.tar" ]; then
  echo "[2/4] 모델 캐시 적용 (컨테이너보다 먼저 넣어야 어댑터가 오프라인으로 뜬다)"
  bash scripts/import-hf-cache.sh "$WORK/hf-cache.tar"
else
  echo "[2/4] 모델 캐시 없음 — 건너뜀"
fi

echo "[3/4] 컨테이너 빌드·기동 (처음이면 5~10분)"
docker compose up -d --build

echo "[4/4] 운영 DB 데이터 적용"
until docker compose ps --format '{{.Service}} {{.Status}}' | grep -q "mariadb.*healthy"; do sleep 3; done
mkdir -p .server/mariadb && cp "$WORK"/mariadb/*.sql .server/mariadb/
if [ -f .server/mariadb/security_monitoring.sql ]; then
  bash scripts/import-db-dump.sh .server/mariadb/luck_db.sql .server/mariadb/security_monitoring.sql
else
  bash scripts/import-db-dump.sh .server/mariadb/luck_db.sql
fi
rm -rf "$WORK"
echo
echo "완료. 브라우저에서 http://localhost 를 여세요 (Grafana: http://localhost:3000)."
