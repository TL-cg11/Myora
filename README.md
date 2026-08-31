# luck-nginx

Ubuntu 24.04 기반 NGINX 프록시 서버 구성용 저장소입니다.

## 역할
- 외부 HTTP/HTTPS 요청을 수신합니다.
- FastAPI 백엔드 서버인 `luck-was`로 요청을 전달합니다.
- `/health` 체크 경로를 제공해 상태 확인이 가능하게 구성합니다.

## 배치 구조
- `nginx.conf`: 전역 NGINX 설정
- `conf.d/luck.conf`: 서비스별 서버 블록
- `scripts/install.sh`: NGINX 설치 및 구성 자동화

## 설치
```bash
cd ~/luck-nginx
bash scripts/install.sh
```

## 테스트
```bash
curl -I http://127.0.0.1/
curl http://127.0.0.1/health
```

## 연동 대상
- FastAPI: `http://127.0.0.1:8000`

## 보안 참고
- 실서비스에서는 Let's Encrypt 또는 자체 TLS 인증서를 적용해 HTTPS를 활성화하세요.
- `server_name`과 도메인을 실제 서비스 이름에 맞게 변경하세요.
