# luck-was

Ubuntu 24.04 기반 FastAPI 백엔드 애플리케이션 저장소입니다.

## 역할
- REST API를 제공합니다.
- MariaDB 연결 상태를 확인할 수 있습니다.
- NGINX에서 프록시할 기본 엔드포인트를 제공합니다.

## 구조
- `app/main.py`: FastAPI 엔트리포인트
- `app/db.py`: MariaDB 연결 예제
- `app/config.py`: 환경 변수 기반 설정
- `scripts/install.sh`: 서버 설치 및 실행 준비
- `scripts/run.sh`: 로컬 실행 스크립트

## 설치
```bash
cd ~/luck-was
bash scripts/install.sh
```

## 로컬 테스트
```bash
bash scripts/run.sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/
```

## 연결 정보
- 기본 포트: `8000`
- DB 호스트: `127.0.0.1`
- DB 이름: `luck_db`

## 참고
- `.env.example` 파일을 복사해 `.env`를 구성하고 실제 정보를 입력하세요.
- 배포 시에는 `systemd` 서비스 파일을 사용해 자동 시작을 구성하세요.
