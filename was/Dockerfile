# syntax=docker/dockerfile:1.7
# luck-was: React 프론트를 빌드해 dist/ 에 넣고 FastAPI(uvicorn)로 서빙하는 이미지.
# 같은 이미지를 Kafka 마스킹 어댑터(security-monitoring/detector)에도 사용한다.
# amd64(Windows/Intel Mac)와 arm64(Apple Silicon) 모두 공식 base 이미지가 지원한다.

# ---------- 1단계: 프론트엔드 빌드 ----------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json vite.config.js index.html ./
COPY scripts/prepare-face-assets.mjs scripts/
# 저장소에 이미 들어 있는 얼굴 모델(3.6MB)을 재사용해 빌드 중 외부 다운로드를 피한다.
# prepare-face-assets.mjs 는 1MB 이상 파일이 있으면 다운로드를 건너뛴다.
COPY dist/mediapipe/models/face_landmarker.task public/mediapipe/models/face_landmarker.task
RUN npm ci
COPY src src
RUN npm run build

# ---------- 2단계: 런타임 ----------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY app app
COPY consumer consumer
COPY schemas schemas
COPY security-monitoring security-monitoring
COPY --from=frontend /build/dist dist
RUN useradd --system --uid 10001 --create-home was && chown -R was:was /app
USER was
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------- 3단계: 마스킹 어댑터 + 한국어 NER/문맥 모델 런타임 ----------
# 운영 서버의 어댑터는 KoELECTRA NER 과 KLUE NLI 문맥 재검증을 켜고 돈다. CPU 전용 torch 를
# 설치해 이미지 크기를 줄인다(기본 PyPI torch 는 CUDA 라이브러리까지 끌어와 수 GB 가 된다).
# compose 에서 masking-adapter 의 build target 으로 선택한다 (ADAPTER_BUILD_TARGET=adapter-ner).
FROM runtime AS adapter-ner
USER root
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.6,<3"  && pip install "transformers>=4.41,<6"
# 모델 캐시는 볼륨(/hf-cache)에 둔다. 서버의 ~/.cache/huggingface 를 그대로 복사해 오프라인으로 쓴다.
ENV HF_HOME=/hf-cache
RUN install -d -o was -g was -m 0755 /hf-cache
USER was
