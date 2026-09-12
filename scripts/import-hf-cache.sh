#!/usr/bin/env bash
# NER/문맥 모델 캐시(KoELECTRA NER, KLUE NLI ≈ 900MB)를 compose 의 hf-cache 볼륨에 넣는다.
#   bash scripts/import-hf-cache.sh                 # 운영 WAS 서버(was@100.66.77.55)에서 SSH 로 복사
#   bash scripts/import-hf-cache.sh user@host       # 다른 서버에서 복사
#   bash scripts/import-hf-cache.sh hf-cache.tar    # 팀 번들의 tar 파일에서 복사 (서버 접근 불필요)
# 둘 다 없으면 첫 실행 때 인터넷에서 내려받는다(HF_HUB_OFFLINE=0).
set -euo pipefail
# Windows Git Bash 가 /경로 인자를 C:\Program Files\Git\... 로 바꾸는 것을 막는다 (docker 인자 보호).
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
SRC=${1:-was@100.66.77.55}
VOLUME=$(docker compose config --format json | python -c "import sys,json; d=json.load(sys.stdin); print(d['volumes']['hf-cache'].get('name') or d['name']+'_hf-cache')")
docker volume create "$VOLUME" >/dev/null
if [ -f "$SRC" ]; then
  echo "복사: $SRC → 볼륨 $VOLUME"
  docker run --rm -i -v "$VOLUME":/hf-cache alpine sh -c 'tar -xf - -C /hf-cache && chown -R 10001:10001 /hf-cache && du -sh /hf-cache/hub/*' < "$SRC"
else
  echo "복사: $SRC:~/.cache/huggingface/hub → 볼륨 $VOLUME"
  ssh -o BatchMode=yes "$SRC" 'cd ~/.cache/huggingface && tar -cf - hub'     | docker run --rm -i -v "$VOLUME":/hf-cache alpine sh -c 'tar -xf - -C /hf-cache && chown -R 10001:10001 /hf-cache && du -sh /hf-cache/hub/*'
fi
echo "완료. .env 의 DETECTOR_*_ENABLED=true, *_LOCAL_FILES_ONLY=true, HF_HUB_OFFLINE=1 로 두면 오프라인으로 동작한다."
