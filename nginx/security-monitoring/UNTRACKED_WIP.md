# Nginx 서버에서 가져온 미커밋 초안 (2026-09-09)

`docker-compose.yml`, `grafana/`, `loki/`, `vector/` 는 Nginx 서버 `~/luck-nginx/security-monitoring/` 에
untracked 상태로 남아 있던 작업물이다 (Suricata `eve.json` → Vector → Kafka `luck.security.ids.v1` → Loki → Grafana
`suricata-ddos` 대시보드). 서버에는 Docker 가 설치돼 있지 않아 **실행된 적이 없고**, 실제로 동작 중인 경로는
`classifier/ids_classifier.py` → `/var/log/luck-security/ids-events.jsonl` 이다.

저장소 루트의 `docker-compose.yml`(전체 스택)과는 별개이며, 유실 방지를 위해 그대로 보관한다.
이어서 작업하려면 topic 이름을 루트 스택의 `myohan.*` 규칙에 맞추고 Kafka/Loki 를 루트 스택 것과 공유하도록 바꾼다.
