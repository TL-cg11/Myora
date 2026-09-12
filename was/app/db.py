from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


DATABASE_URL = settings.database_url or URL.create(
    drivername="mysql+pymysql",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
    query={"charset": "utf8mb4"},
)

engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"check_same_thread": False} if str(DATABASE_URL).startswith("sqlite:") else {"connect_timeout": 3},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 의존성. 요청 하나당 세션 하나."""
    with SessionLocal() as session:
        yield session


def check_db() -> dict:
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                count = conn.execute(text("SELECT COUNT(*) FROM saju_term")).scalar_one()
                return {"status": "ok" if count else "error", "result": "local sqlite", "dictionary_entries": count}
            row = conn.execute(
                text(
                    "SELECT status, checked_at "
                    "FROM health_check ORDER BY id DESC LIMIT 1"
                )
            ).mappings().one()
            return {
                "status": "ok",
                "result": row["status"],
                "checked_at": row["checked_at"].isoformat(),
            }
    except Exception as exc:  # pragma: no cover - runtime health check
        return {"status": "error", "message": str(exc)}
