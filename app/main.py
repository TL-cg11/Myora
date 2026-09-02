from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import check_db
from app.routers.chat import router as chat_router
from app.routers.pages import DIST_DIR, router as pages_router

app = FastAPI(title=settings.app_name, version="1.0.0")


@app.get("/health")
def health() -> JSONResponse:
    db_status = check_db()
    if db_status["status"] == "ok":
        return JSONResponse(
            {"status": "ok", "service": settings.app_name, "database": db_status}
        )
    return JSONResponse(
        {"status": "degraded", "service": settings.app_name, "database": db_status},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "service": settings.app_name}


app.include_router(chat_router)
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
app.mount(
    "/mediapipe",
    StaticFiles(directory=DIST_DIR / "mediapipe"),
    name="mediapipe",
)
app.include_router(pages_router)
