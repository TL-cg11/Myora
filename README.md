# luck-mariadb

Ubuntu 24.04 기반 MariaDB 서버 설정 저장소입니다.

## 역할
- 데이터베이스 서버를 구동합니다.
- 애플리케이션용 DB와 사용자를 생성합니다.
- 초기 스키마를 적용합니다.

## 구조
- `mariadb.cnf`: 기본 MariaDB 설정
- `sql/init/01_init.sql`: 초기 DB 및 사용자 생성 SQL
- `scripts/install.sh`: MariaDB 설치 및 초기화
- `scripts/test.sh`: 연결 확인

## 설치
```bash
cd ~/luck-mariadb
bash scripts/install.sh
```

## 연결 테스트
```bash
bash scripts/test.sh
mysql -u luck_user -p -h 127.0.0.1 luck_db
```

## 기본 값
- DB 이름: `luck_db`
- 사용자: `luck_user`
- 포트: `3306`

## 참고
- 실제 운영 환경에서는 강한 비밀번호와 방화벽 규칙을 적용하세요.
- `mariadb.cnf`에서 bind-address, character-set, log 설정을 상황에 맞게 조정하세요.
