# luck-mariadb

Ubuntu Server 24.04에서 동작하는 MariaDB 테스트 서버 구성입니다. FastAPI 서버 한 대에만 애플리케이션 계정 로그인을 허용하고 상태 확인용 테이블을 초기화합니다.

## 구성

- MariaDB 서버: `100.104.124.29:3306`
- 허용된 WAS 주소: `100.66.77.55`
- 데이터베이스: `luck_db`
- 애플리케이션 사용자: `luck_user`
- 초기 테이블: `health_check`

## 설치 및 갱신

```bash
git clone https://github.com/TL-cg11/luck-mariadb.git ~/luck-mariadb
cd ~/luck-mariadb
bash scripts/install.sh
```

이미 clone한 서버에서는 다음과 같이 갱신합니다.

```bash
cd ~/luck-mariadb
git pull --ff-only
bash scripts/install.sh
```

필요하면 설치 시 값을 덮어쓸 수 있습니다.

```bash
DB_PASSWORD='새-비밀번호' WAS_HOST='WAS-IP' bash scripts/install.sh
```

## 확인

```bash
bash scripts/test.sh
sudo ss -ltnp | grep 3306
sudo systemctl status mariadb --no-pager
```

`mariadb.cnf`는 원격 WAS 접속을 위해 TCP 리스닝을 활성화합니다. 데이터베이스 계정은 지정한 WAS 주소와 로컬호스트에서만 인증됩니다. 인터넷에 직접 포트를 공개하지 말고 Tailscale 또는 방화벽으로 접근 범위를 제한하세요.
