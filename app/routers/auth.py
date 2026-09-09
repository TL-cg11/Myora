from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import bearer_token, create_session, current_user, hash_password, token_digest, verify_password
from app.db import get_session
from app.models import AppUser, AuthSession, Reading, TarotReading

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    email: str


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
    return UserOut(id=user.id, username=user.username, name=user.name, email=user.email)


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


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, session: Session = Depends(get_session)) -> AuthOut:
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
    return AuthOut(access_token=token, expires_at=expires_at, user=user_out(user))


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, session: Session = Depends(get_session)) -> AuthOut:
    login_id = payload.login_id.strip().lower()
    user = session.scalar(select(AppUser).where(or_(AppUser.username == login_id, AppUser.email == login_id)))
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않아요.")
    claim_guest_readings(session, user, payload.guest_key)
    session.commit()
    token, expires_at = create_session(session, user)
    return AuthOut(access_token=token, expires_at=expires_at, user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: AppUser = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict:
    token = bearer_token(authorization)
    if token:
        auth_session = session.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        if auth_session:
            session.delete(auth_session)
            session.commit()
    return {"status": "ok"}
