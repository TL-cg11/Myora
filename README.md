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
