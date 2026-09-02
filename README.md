# luck-was

Ubuntu Server 24.04에서 동작하는 FastAPI 테스트 애플리케이션입니다. Nginx의 요청을 받고 별도 MariaDB 서버의 `health_check` 테이블을 조회합니다.

## 구성

- FastAPI 서버: `100.66.77.55:8000`
- MariaDB 서버: `100.104.124.29:3306`
- `GET /`: 3개 서비스의 상태를 보여주는 테스트 대시보드
- `GET /api/health`: WAS 자체 상태(liveness)
- `GET /health`: MariaDB 스키마와 데이터까지 확인(readiness)

## 설치 및 갱신

```bash
git clone https://github.com/TL-cg11/luck-was.git ~/luck-was
cd ~/luck-was
cp .env.example .env
bash scripts/install.sh
```

이미 clone한 서버에서는 다음과 같이 갱신합니다.

```bash
cd ~/luck-was
git pull --ff-only
bash scripts/install.sh
```

`scripts/install.sh`는 Python 가상환경과 의존성을 구성하고 `luck-was.service`를 설치해 부팅 시 자동 시작되게 합니다.

## 확인

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/health
sudo systemctl status luck-was --no-pager
```

`.env.example`의 계정은 테스트 전용입니다. 운영 환경에서는 `.env`에 별도 비밀번호를 설정하고 MariaDB 사용자 비밀번호도 동일하게 변경하세요.

## 프론트엔드

React + Vite로 만든 묘한운세 랜딩 페이지입니다.

### 실행

```bash
npm install
npm run dev
```

### 페이지

- `/` 메인
- `/saju` 사주
- `/tarot` 타로
- `/face` 관상

## 타로

카드 뽑기와 해석은 서버가 정합니다. 화면에서 카드를 고르더라도 어떤 카드가 나왔는지는
서버가 결정해야 결과를 조작할 수 없습니다. 리딩 조회는 `guest_key` 가 일치할 때만 됩니다.

스키마와 기준 데이터는 `luck-mariadb` 의 `sql/init/02~04` 에 있습니다.

### 결과 채팅 (DeepSeek)

`.env` 에 키를 넣으면 켜지고, 비워두면 카드에서 바로 끌어오는 규칙 기반 답변으로
동작합니다. 호출이 실패해도 같은 답변으로 되돌아가므로 채팅이 끊기지는 않습니다.

```
DEEPSEEK_TAROT_API_KEY=sk-...
DEEPSEEK_TAROT_MODEL=deepseek-v4-flash
LLM_TIMEOUT=20
```

응답의 `source` 가 이번 답변을 무엇으로 만들었는지 알려줍니다(`llm` / `rule`).
화면에서는 채팅 패널 오른쪽 위 배지로 보입니다.

`DEEPSEEK_BASE_URL` 은 관상 채팅과 공용입니다.

리딩 요약은 LLM 을 쓰지 않습니다. 카드를 뽑는 순간에 외부 API 를 기다리게 하지
않으려는 것이고, 바꾸려면 `app/services/tarot.py` 의 주석을 보세요.
