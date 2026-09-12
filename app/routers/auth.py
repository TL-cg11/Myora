from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE_NAME,
    bearer_token,
    clear_session_cookie,
    create_session,
    current_user,
    hash_password,
    require_admin,
    set_session_cookie,
    token_digest,
    utc_now,
    verify_password,
)
from app.config import settings
from app.db import get_session
from app.models import AppUser, AppUserRole, AuthSession, Reading, TarotReading

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    email: str
    role: AppUserRole


class RegisterIn(BaseModel):
    username: str = Field(min_length=4, max_length=40, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    email: str = Field(min_length=5, max_length=190)
    guest_key: UUID | None = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[1]:
            raise ValueError("올바른 이메일 주소를 입력해 주세요.")
        return value


class LoginIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=190)
    password: str = Field(min_length=1, max_length=128)
    guest_key: UUID | None = None


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


def user_out(user: AppUser) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        name=user.name,
        email=user.email,
        role=user.role,
    )


def claim_guest_readings(session: Session, user: AppUser, guest_key: UUID | None) -> None:
    if guest_key is None:
        return
    key = str(guest_key)
    session.execute(
        update(Reading).where(Reading.guest_key == key, Reading.user_id.is_(None))
        .values(user_id=user.id, guest_key=None)
    )
    # 로컬 SQLite는 사주 개발용이라 타로 테이블을 만들지 않는다.
    if session.get_bind().dialect.name != "sqlite":
        session.execute(
            update(TarotReading).where(TarotReading.guest_key == key, TarotReading.user_id.is_(None))
            .values(user_id=user.id, guest_key=None)
        )


def locked_error(locked_until: datetime, now: datetime) -> HTTPException:
    retry_after = max(1, ceil((locked_until - now).total_seconds()))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="로그인에 여러 번 실패해 계정이 1시간 동안 잠겼어요. 잠시 후 다시 시도해 주세요.",
        headers={"Retry-After": str(retry_after)},
    )


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, response: Response, session: Session = Depends(get_session)) -> AuthOut:
    email = payload.email
    if session.scalar(select(AppUser.id).where(or_(AppUser.username == payload.username, AppUser.email == email))):
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디 또는 이메일이에요.")
    user = AppUser(
        username=payload.username,
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        status="active",
    )
    session.add(user)
    try:
        session.flush()
        claim_guest_readings(session, user, payload.guest_key)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디 또는 이메일이에요.") from exc
    token, expires_at = create_session(session, user)
    set_session_cookie(response, token, expires_at)
    return AuthOut(access_token=token, expires_at=expires_at, user=user_out(user))


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, response: Response, session: Session = Depends(get_session)) -> AuthOut:
    login_id = payload.login_id.strip().lower()
    user = session.scalar(
        select(AppUser)
        .where(or_(AppUser.username == login_id, AppUser.email == login_id))
        .with_for_update()
    )
    now = utc_now()
    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise locked_error(user.locked_until, now)

    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        if user is not None and user.status == "active":
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.auth_max_failed_attempts:
                user.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
                # 잠긴 계정은 이미 발급된 세션으로도 접근하지 못하게 즉시 폐기한다.
                session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                session.commit()
                raise locked_error(user.locked_until, now)
            session.commit()
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않아요.")

    user.failed_login_attempts = 0
    user.locked_until = None
    claim_guest_readings(session, user, payload.guest_key)
    session.commit()
    token, expires_at = create_session(session, user)
    set_session_cookie(response, token, expires_at)
    return AuthOut(access_token=token, expires_at=expires_at, user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: AppUser = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.post("/logout")
def logout(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    session: Session = Depends(get_session),
) -> dict:
    token = bearer_token(authorization) or session_cookie
    if token:
        auth_session = session.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        if auth_session:
            session.delete(auth_session)
            session.commit()
    # DB 세션이 이미 없었더라도(만료 등) 브라우저에 남은 cookie는 그대로면 다음
    # 요청에도 계속 실려 나간다. 항상 지운다.
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/admin-check", status_code=status.HTTP_204_NO_CONTENT)
def admin_check(user: AppUser = Depends(require_admin)) -> Response:
    """nginx auth_request가 그대로 호출하는 관리자 검증 endpoint.

    Grafana iframe 같은 auth_request 경로는 원래 요청의 Authorization 헤더를
    기본적으로 전달하지 않으므로, 실제로는 SESSION_COOKIE_NAME cookie로만
    인증된다(require_admin -> current_user -> optional_user가 Authorization을
    먼저 보고 없으면 cookie를 본다). 응답 본문은 nginx가 보지 않으므로 비운다.

    - 관리자: 204
    - 미인증: 401 (current_user에서)
    - 일반 계정: 403 (require_admin에서)
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)
