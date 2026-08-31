# luck-nginx

Ubuntu Server 24.04에서 외부 HTTP 요청을 받고 별도 FastAPI 서버로 전달하는 Nginx 구성입니다.

## 구성

- Nginx 서버: `100.117.253.9:80`
- FastAPI 업스트림: `100.66.77.55:8000`
- `GET /nginx-health`: Nginx 자체 상태 확인
- `GET /health`: FastAPI와 MariaDB까지 포함한 전체 상태 확인
- 그 밖의 요청: FastAPI로 프록시

## 설치 및 갱신

```bash
git clone https://github.com/TL-cg11/luck-nginx.git ~/luck-nginx
cd ~/luck-nginx
bash scripts/install.sh
```

이미 clone한 서버에서는 다음과 같이 갱신합니다.

```bash
cd ~/luck-nginx
git pull --ff-only
bash scripts/install.sh
```

## 확인

```bash
curl http://127.0.0.1/nginx-health
curl http://127.0.0.1/health
curl http://127.0.0.1/
```

현재 구성은 Tailscale 사설 주소를 사용하는 테스트 환경용 HTTP 구성입니다. 인터넷에 공개할 때는 도메인, TLS 인증서, 방화벽 정책을 추가하세요.
