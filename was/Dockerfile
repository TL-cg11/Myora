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
FROM python:3.12-slim
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
