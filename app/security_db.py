"""security_monitoring 전용 SQLAlchemy 연결과 인증 사용자 조회."""

from collections.abc import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import settings
from app.security_models import SecurityUser


SECURITY_DATABASE_URL = settings.security_database_url or URL.create(
    drivername="mysql+pymysql",
    username=settings.security_db_user,
    password=settings.security_db_password,
    host=settings.security_db_host,
    port=settings.security_db_port,
    database=settings.security_db_name,
    query={"charset": "utf8mb4"},
)

security_engine: Engine = create_engine(
    SECURITY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=(
        {"check_same_thread": False}
        if str(SECURITY_DATABASE_URL).startswith("sqlite:")
        else {"connect_timeout": 3}
    ),
    future=True,
)
SecuritySessionLocal = sessionmaker(
    bind=security_engine, autoflush=False, expire_on_commit=False
)


def get_security_session() -> Iterator[Session]:
    with SecuritySessionLocal() as session:
        yield session


def find_security_user(actor_id: str) -> SecurityUser | None:
    """인증 middleware에서 사용할 활성 여부·역할 포함 사용자 조회."""
    with SecuritySessionLocal() as session:
        statement = (
            select(SecurityUser)
            .where(SecurityUser.actor_id == actor_id)
            .options(selectinload(SecurityUser.roles))
        )
        return session.scalars(statement).one_or_none()
