#!/usr/bin/env bash
# 운영 WAS 서버의 Hugging Face 모델 캐시(KoELECTRA NER, KLUE NLI ≈ 900MB)를 compose 의 hf-cache
# 볼륨으로 복사한다. 서버 SSH 키 접근이 있는 사람이 한 번 실행하면 되고, 없으면 첫 실행 때
# 인터넷에서 내려받는다(HF_HUB_OFFLINE=0).
#   bash scripts/import-hf-cache.sh [user@host]   (기본 was@100.66.77.55)
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=${1:-was@100.66.77.55}
VOLUME=$(docker compose config --format json | python -c "import sys,json; d=json.load(sys.stdin); print(d['volumes']['hf-cache'].get('name') or d['name']+'_hf-cache')")
echo "복사: $HOST:~/.cache/huggingface/hub → 볼륨 $VOLUME"
docker volume create "$VOLUME" >/dev/null
ssh -o BatchMode=yes "$HOST" 'cd ~/.cache/huggingface && tar -cf - hub' \
  | docker run --rm -i -v "$VOLUME":/hf-cache alpine sh -c 'tar -xf - -C /hf-cache && chown -R 10001:10001 /hf-cache && du -sh /hf-cache/hub/*'
echo "완료. .env 의 DETECTOR_*_ENABLED=true, *_LOCAL_FILES_ONLY=true, HF_HUB_OFFLINE=1 로 두면 오프라인으로 동작한다."
