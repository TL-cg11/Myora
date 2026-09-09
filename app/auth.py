"""비밀번호 해시와 폐기 가능한 Bearer 세션 인증."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.config import settings
from app.models import AppUser, AuthSession

PBKDF2_ITERATIONS = 310_000

def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session, user: AppUser) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(hours=settings.auth_session_hours)
    session.add(AuthSession(user_id=user.id, token_hash=token_digest(token), expires_at=expires_at))
    session.commit()
    return token, expires_at


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def optional_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> AppUser | None:
    token = bearer_token(authorization)
    if token is None:
        return None
    auth_session = session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_digest(token),
            AuthSession.expires_at > utc_now(),
            # 정책 변경 전에 길게 발급된 세션도 생성 시각 기준 1시간만 허용한다.
            AuthSession.created_at > utc_now() - timedelta(hours=settings.auth_session_hours),
        )
    )
    if auth_session is None or auth_session.user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 만료되었어요. 다시 로그인해 주세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_session.user


def current_user(user: AppUser | None = Depends(optional_user)) -> AppUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요해요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
