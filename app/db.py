from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings


DATABASE_URL = (
    f"mysql+pymysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:"
    f"{settings.db_port}/{settings.db_name}?charset=utf8mb4"
)

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def check_db() -> dict:
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 AS ok")).scalar_one()
            return {"status": "ok", "result": result}
    except Exception as exc:  # pragma: no cover - runtime health check
        return {"status": "error", "message": str(exc)}
