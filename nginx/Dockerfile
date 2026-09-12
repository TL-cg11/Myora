# syntax=docker/dockerfile:1.7
# luck-nginx 저장소의 Python 워커(security_sink.*)용 이미지.
# Nginx 자체는 공식 nginx:alpine 이미지에 docker/ 의 설정을 마운트해서 쓴다.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-security-sink.txt ./
RUN pip install -r requirements-security-sink.txt
COPY security_sink security_sink
COPY scripts scripts
COPY contracts contracts
COPY fixtures fixtures
COPY tests tests
RUN useradd --system --uid 10002 --create-home sink \
 && install -d -o sink -g sink -m 0700 /var/lib/luck-security-sink/masked-log-buffer \
 && chown -R sink:sink /app
USER sink
# 실행 모듈은 compose 의 command 로 정한다:
#   python -m security_sink.worker / masked_worker / notifier_worker / scripts.run_security_retention
CMD ["python", "-m", "security_sink.worker"]
