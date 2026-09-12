# Myora (묘한운세)

고양이 상담사 '묘라'가 사주·타로·관상을 봐주는 웹 서비스와, 그 서비스의 로그를 수집해
개인정보를 마스킹하고 보안 이벤트를 저장·시각화하는 보안 모니터링 파이프라인.

이 저장소는 기존 `luck-nginx`, `luck-was`, `luck-mariadb` 세 저장소를 커밋 이력째 합친
모노레포이며, **Docker Compose 한 번으로 전체 스택이 로컬(Windows / macOS / Linux)에서 뜬다.**

```
Myora/
├── docker-compose.yml   전체 스택 정의
├── .env.example         로컬 설정 예시 → .env 로 복사해서 사용
├── nginx/               (구 luck-nginx) 리버스 프록시, 보안 이벤트 sink, 관측 스택, Suricata
│   ├── docker/          compose 전용 nginx·fluent-bit·loki·prometheus·grafana 설정
│   └── Dockerfile       security_sink 워커 이미지
├── was/                 (구 luck-was) FastAPI 백엔드 + React 프론트 + Kafka 로깅 + PII 탐지기
│   └── Dockerfile       프론트 빌드 → uvicorn 이미지 (마스킹 어댑터도 같은 이미지)
└── mariadb/             (구 luck-mariadb) 스키마 SQL, 마이그레이션
    └── docker/          compose 전용 초기화 스크립트
```

## 빠른 시작

필요한 것: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows·Mac 모두 지원,
Apple Silicon 포함). 그 외 Node·Python 설치는 필요 없다.

```bash
git clone https://github.com/TL-cg11/Myora.git
cd Myora
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
docker compose up -d --build
```

첫 실행은 이미지 빌드와 DB 초기화 때문에 3~5분 걸린다. 진행 상황은 `docker compose logs -f` 로 본다.

| 주소 | 내용 |
|---|---|
| http://localhost | 묘한운세 사이트 (`/saju`, `/tarot`, `/face`, `/login`, `/mypage`) |
| http://localhost/health | Nginx → WAS → MariaDB 전체 상태 |
| http://localhost:3000 | Grafana (`admin` / `.env` 의 `GRAFANA_ADMIN_PASSWORD`) — Security Monitoring 폴더에 대시보드 2개 |
| http://127.0.0.1:8000 | WAS 직접 접속 (디버깅용, 로컬에서만) |
| 127.0.0.1:3306 | MariaDB (`luck_user` / `.env` 의 `LUCK_DB_PASSWORD`) |
| 127.0.0.1:9092 | Kafka (호스트에서 `kafka-console-consumer` 등으로 topic 확인) |

관상(`/face`)은 카메라를 쓰는데, 브라우저는 `http://localhost` 를 보안 컨텍스트로 취급하므로
HTTPS 없이도 카메라 권한이 정상적으로 동작한다. `127.0.0.1` 대신 반드시 `localhost` 로 접속한다.

AI 채팅(DeepSeek)을 쓰려면 `.env` 의 `DEEPSEEK_API_KEY` 를 채우고 `docker compose up -d was` 로
재시작한다. 키가 없으면 채팅은 검수된 고정 안내(`source: rule`)만 돌려주고 타로의 "질문 검사"는
503 을 반환해 질문 없이 진행하게 되며, 사주·타로·관상 결과 자체는 정상 동작한다.

알아 둘 것:

- 타로 카드 그림(`/assets/tarot/major-XX.png`)은 원래 저장소에도 없어서 404 가 찍히고, 화면은
  설계대로 번호·이름 카드로 대체 표시한다.
- 로그인은 5회 연속 실패하면 60분 잠긴다(`AUTH_*` 로 조정). 로컬에서 잠겼으면
  `docker compose exec mariadb mariadb -uroot -p$MARIADB_ROOT_PASSWORD luck_db -e "UPDATE app_user SET failed_login_attempts=0, locked_until=NULL"` 로 푼다.

### 자주 쓰는 명령

```bash
docker compose ps                         # 컨테이너 상태
docker compose logs -f was                # 특정 서비스 로그 (nginx, masking-adapter, security-event-sink ...)
docker compose up -d --build was          # 코드 수정 후 WAS 만 다시 빌드
docker compose down                       # 중지 (데이터 유지)
docker compose down -v                    # 중지 + DB·Loki·Grafana 데이터 삭제 (DB 초기화 다시 실행됨)
docker compose --profile notify up -d     # Discord 알림 워커 추가 (DISCORD_WEBHOOK_URL 필요)
docker compose --profile retention up -d  # 보존 기간 정리 워커 추가
```

### 보안 관제 API 확인

`.env.example` 의 기본 토큰은 `myora-local-security-token` 이고 `local-admin`(ADMIN) 사용자에 연결돼 있다.

```bash
curl -H "Authorization: Bearer myora-local-security-token" \
  "http://localhost/api/security/events?page=1&page_size=20"
curl -H "Authorization: Bearer myora-local-security-token" \
  "http://localhost/api/security/audit-logs"
```

### 전체 파이프라인 확인

사이트에서 타로 한 번 뽑으면 다음 순서로 흘러간다.

1. Nginx 가 `access.json.log` 기록 → Fluent Bit → Kafka `myohan.nginx.access`
2. WAS 가 `api_request` 로그 → Kafka `myohan.was.app`
3. `masking-adapter` 가 두 topic 을 읽어 마스킹 → `myohan.masked-logs`, 탐지가 있으면 `myohan.security-events`
4. `masked-log-sink` → Loki, `security-event-sink` → MariaDB `security_monitoring`
5. Grafana 에서 Loki 로그와 MariaDB 이벤트를 조회

```bash
docker compose logs masking-adapter security-event-sink masked-log-sink | tail -50
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic myohan.masked-logs --from-beginning --max-messages 3
```

## 개발

### 프론트엔드만 빠르게 고칠 때

컨테이너의 WAS 를 백엔드로 두고 Vite dev 서버를 쓴다 (`vite.config.js` 가 `/api` 를 `127.0.0.1:8000` 으로 프록시).

```bash
cd was
npm install
npm run dev        # http://localhost:5173
```

### 테스트

```bash
# WAS 백엔드 (컨테이너 안에서)
docker compose exec was python -m unittest discover -s app/tests
# PII 탐지기
docker compose exec -w /app/security-monitoring/detector was python -m unittest discover -s tests
# 보안 sink
docker compose exec security-event-sink python -m unittest discover -s tests
# 프론트
cd was && npm test
```

## 구조

```
브라우저 → nginx(:80) ────────────→ was(:8000) ─────────→ mariadb(:3306)
              │ access.json.log        │ myohan.was.app       luck_db / security_monitoring
              ▼                        ▼
          fluent-bit ────────────→ kafka ◀──────── masking-adapter (was 와 네트워크 공유,
          myohan.nginx.access          │            채팅 화면 마스킹 API 127.0.0.1:8765 제공)
                                       │ myohan.masked-logs / myohan.security-events
                                       ▼
                 security-event-sink → mariadb        masked-log-sink → loki
                            └── prometheus (metrics :9108/:9109) ── grafana(:3000)
```

기존 3대 서버 구성(Tailscale IP)과 다른 점:

| 항목 | 서버 3대 | Docker Compose |
|---|---|---|
| 서버 간 주소 | `100.x.x.x` Tailscale IP | compose 서비스 이름 (`was`, `mariadb`, `kafka`) |
| HTTPS | Tailscale Serve `*.ts.net` | 없음. `http://localhost` 가 보안 컨텍스트라 카메라 동작 |
| DB 계정 허용 호스트 | WAS IP 고정 | `%` (compose 네트워크 밖으로 3306 을 열지 않음) |
| Suricata IDS / EveBox | Nginx 서버에 설치 | 미포함 (호스트 NIC 필요). `nginx/security-monitoring/README.md` 참고 |
| Discord 알림 / 보존 정리 | systemd 서비스·타이머 | `--profile notify`, `--profile retention` |
| Kafka | WAS 서버에 설치 | `apache/kafka` KRaft 단일 노드 (데이터는 컨테이너 재생성 시 초기화) |

## 기존 서버 배포

세 서버(nginx / was / mariadb)에 그대로 배포하는 절차는 각 하위 폴더의 README 와
`scripts/install.sh` 가 그대로 유효하다. 서버에서는 하위 폴더만 사용한다.

```bash
git clone https://github.com/TL-cg11/Myora.git
cd Myora/was && bash scripts/install.sh      # WAS 서버
cd Myora/nginx && bash scripts/install.sh    # Nginx 서버
cd Myora/mariadb && bash scripts/install.sh  # MariaDB 서버
```

기존 MariaDB 에는 새로 추가된 `mariadb/sql/init/16_ai_guardrail.sql` 을 한 번 적용한다
(`app_user.role`, `chat_message.policy_version`, `tarot_chat_message.policy_version`).

```bash
sudo mysql -uroot luck_db < sql/init/16_ai_guardrail.sql
```

## 세부 문서

- [was/README.md](was/README.md) — API, 사주 사전, 타로, AI 가드레일, Kafka 로깅
- [was/AI_GUARDRAIL_POLICY.md](was/AI_GUARDRAIL_POLICY.md) — AI 상담 가드레일 정책
- [was/security-monitoring/detector/README.md](was/security-monitoring/detector/README.md) — PII 탐지기·마스킹 어댑터
- [nginx/README.md](nginx/README.md) — 보안 이벤트 sink, 알림, Suricata
- [nginx/docs/](nginx/docs/) — 관측 스택, 알림, 운영 절차
- [mariadb/README.md](mariadb/README.md) — 스키마 설명
