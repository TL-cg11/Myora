"""보안 관제 API용 fail-closed Bearer 인증과 RBAC."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.security_models import SecurityRoleCode, SecurityUser, SecurityUserStatus


class Permission(str, Enum):
    EVENT_READ = "event:read"
    AUDIT_READ = "audit:read"
    DASHBOARD_READ = "dashboard:read"
    EVENT_STATUS_UPDATE = "event:status:update"
    EVENT_ASSIGN = "event:assign"
    EVENT_FALSE_POSITIVE = "event:false-positive"
    EVENT_REOPEN = "event:reopen"
    USER_MANAGE = "user:manage"
    ROLE_MANAGE = "role:manage"
    SYSTEM_MANAGE = "system:manage"


VIEWER_PERMISSIONS = frozenset(
    {Permission.EVENT_READ, Permission.AUDIT_READ, Permission.DASHBOARD_READ}
)
EDITOR_PERMISSIONS = VIEWER_PERMISSIONS | {
    Permission.EVENT_STATUS_UPDATE,
    Permission.EVENT_ASSIGN,
    Permission.EVENT_FALSE_POSITIVE,
    Permission.EVENT_REOPEN,
}
ADMIN_PERMISSIONS = EDITOR_PERMISSIONS | {
    Permission.USER_MANAGE,
    Permission.ROLE_MANAGE,
    Permission.SYSTEM_MANAGE,
}
ROLE_PERMISSIONS: dict[SecurityRoleCode, frozenset[Permission]] = {
    SecurityRoleCode.VIEWER: VIEWER_PERMISSIONS,
    SecurityRoleCode.EDITOR: frozenset(EDITOR_PERMISSIONS),
    SecurityRoleCode.ADMIN: frozenset(ADMIN_PERMISSIONS),
}


@dataclass(frozen=True)
class SecurityPrincipal:
    actor_id: str
    display_name: str
    roles: frozenset[SecurityRoleCode]
    permissions: frozenset[Permission]


def parse_token_hashes(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("SECURITY_AUTH_TOKEN_HASHES must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("SECURITY_AUTH_TOKEN_HASHES must be a JSON object")

    result: dict[str, str] = {}
    for token_hash, actor_id in parsed.items():
        normalized_hash = str(token_hash).lower()
        if len(normalized_hash) != 64 or any(c not in "0123456789abcdef" for c in normalized_hash):
            raise ValueError("security token hashes must be 64-character SHA-256 hex")
        if not isinstance(actor_id, str) or not actor_id or len(actor_id) > 128:
            raise ValueError("security token actor_id must contain 1-128 characters")
        result[normalized_hash] = actor_id
    return result


def principal_from_user(user: SecurityUser) -> SecurityPrincipal:
    role_codes: set[SecurityRoleCode] = set()
    for role in user.roles:
        try:
            role_codes.add(SecurityRoleCode(role.role_code))
        except ValueError:
            continue  # 알 수 없는 역할은 권한을 부여하지 않는다.
    permissions = frozenset(
        permission
        for role_code in role_codes
        for permission in ROLE_PERMISSIONS[role_code]
    )
    return SecurityPrincipal(
        actor_id=user.actor_id,
        display_name=user.display_name,
        roles=frozenset(role_codes),
        permissions=permissions,
    )


class TokenAuthenticator:
    def __init__(
        self,
        token_hashes: dict[str, str],
        user_loader: Callable[[str], SecurityUser | None],
    ) -> None:
        self._token_hashes = token_hashes
        self._user_loader = user_loader

    def authenticate(self, token: str) -> SecurityPrincipal | None:
        candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
        actor_id = next(
            (
                configured_actor
                for configured_hash, configured_actor in self._token_hashes.items()
                if hmac.compare_digest(candidate, configured_hash)
            ),
            None,
        )
        if actor_id is None:
            return None
        user = self._user_loader(actor_id)
        if user is None or user.status != SecurityUserStatus.ACTIVE:
            return None
        return principal_from_user(user)


class SecurityAuthMiddleware(BaseHTTPMiddleware):
    """`/api/security` 경로만 인증하며 기존 운세 API에는 영향을 주지 않는다."""

    def __init__(self, app, authenticator: TokenAuthenticator) -> None:
        super().__init__(app)
        self.authenticator = authenticator

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/security") or request.method == "OPTIONS":
            return await call_next(request)

        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse(
                {"detail": "Bearer authentication required"},
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = await run_in_threadpool(self.authenticator.authenticate, token)
        if principal is None:
            return JSONResponse(
                {"detail": "Invalid or disabled security credential"},
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.security_principal = principal
        return await call_next(request)


def get_security_principal(request: Request) -> SecurityPrincipal:
    principal = getattr(request.state, "security_principal", None)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return principal


def require_permissions(*required: Permission):
    def authorize(request: Request) -> SecurityPrincipal:
        principal = get_security_principal(request)
        missing = set(required) - principal.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient security role",
            )
        return principal

    return authorize
