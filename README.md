# luck-nginx

Ubuntu Server 24.04에서 Tailscale HTTPS 요청을 받고 별도 FastAPI 서버로 전달하는 구성입니다. 브라우저가 신뢰하는 `*.ts.net` 인증서를 Tailscale Serve가 자동으로 관리합니다.

## 구성

- HTTPS 진입점: `https://<nginx-MagicDNS-name>.ts.net:443`
- Tailscale 서버: `100.117.253.9`
- 로컬 Nginx 백엔드: `127.0.0.1:8080` (외부 접근 불가)
- FastAPI 업스트림: `100.66.77.55:8000`
- `GET /nginx-health`: Nginx 자체 상태 확인
- `GET /health`: FastAPI와 MariaDB까지 포함한 전체 상태 확인
- 그 밖의 요청: FastAPI로 프록시

## 설치 및 갱신

먼저 Tailscale 관리자 콘솔의 [DNS 설정](https://login.tailscale.com/admin/dns)에서 다음 두 항목을 활성화해야 합니다.

1. MagicDNS
2. HTTPS Certificates

인증서 도메인은 Certificate Transparency 공개 로그에 기록되므로 서버 이름에 민감한 정보를 사용하지 마세요.

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

설치 스크립트는 다음 흐름을 자동으로 구성합니다.

```text
브라우저 HTTPS :443 → Tailscale Serve → Nginx 127.0.0.1:8080 → FastAPI
```

Tailscale Serve는 `--bg` 모드로 재부팅 후에도 유지되며 TLS 인증서를 자동으로 갱신합니다.

## 확인

```bash
curl http://127.0.0.1:8080/nginx-health
sudo tailscale serve status
bash scripts/test.sh
```

`tailscale serve status`에 표시되는 `https://<machine>.<tailnet>.ts.net` 주소로 접속해야 합니다. Tailscale IP를 사용한 `http://100.117.253.9` 접속은 더 이상 제공하지 않습니다.

카메라는 HTTPS 주소에서만 정상적으로 권한을 요청합니다. 사이트 권한에서 카메라를 허용한 뒤 `/face` 페이지를 사용하세요.

## 보안 모니터링 계약

저장·감사·관측 파트의 Kafka 메시지 계약은 [`contracts/`](contracts/README.md), DB 분리·검증·재시도·DLQ 정책은 [`docs/security-monitoring-foundation.md`](docs/security-monitoring-foundation.md)에서 관리합니다.

Loki·Prometheus·Grafana의 로컬 실행과 health check는 [`docs/observability.md`](docs/observability.md)를 참고합니다.
