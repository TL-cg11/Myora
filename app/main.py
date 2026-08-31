from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import check_db

app = FastAPI(title=settings.app_name, version="1.0.0")


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "status": "ok",
    }


@app.get("/health")
def health() -> JSONResponse:
    db_status = check_db()
    if db_status["status"] == "ok":
        return JSONResponse({"status": "ok", "database": db_status})
    return JSONResponse({"status": "degraded", "database": db_status}, status_code=200)


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "service": settings.app_name}
