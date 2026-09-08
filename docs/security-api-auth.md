# Security API authentication and RBAC

`/api/security` 아래 API는 opaque Bearer token으로 인증한다. 서버는 원문 token을
저장하지 않고 `.env`의 `SECURITY_AUTH_TOKEN_HASHES`에서 SHA-256 hash를 actor ID로
변환한 다음, `security_monitoring.security_user`와 `security_user_role`에서 활성 사용자와
역할을 조회한다. 토큰 누락·불일치·비활성 사용자는 fail-closed 방식으로 거부한다.

권한은 누적된다.

- `VIEWER`: 이벤트 목록·상세, 감사 로그, 대시보드 조회
- `EDITOR`: VIEWER 권한 + 상태 변경, 담당자 지정, 오탐 처리, 재오픈
- `ADMIN`: EDITOR 권한 + 사용자·역할·매핑, 시스템 설정 관리

토큰과 hash 생성 예시:

```bash
TOKEN="$(openssl rand -hex 32)"
printf '%s' "$TOKEN" | sha256sum
```

출력 hash와 actor ID를 JSON으로 `.env`에 설정하고 원문 token은 안전한 비밀 저장소에
보관한다. 예: `SECURITY_AUTH_TOKEN_HASHES={"<64자리 hash>":"operator-a"}`.
동일한 actor ID의 `ACTIVE` 사용자가 DB에 있고 역할 매핑이 있어야 권한이 부여된다.
