from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import check_db
from app.routers.chat import router as chat_router
from app.routers.face import router as face_router
from app.routers.pages import DIST_DIR, router as pages_router
from app.routers.saju import router as saju_router
from app.routers.saju_chat import router as saju_chat_router
from app.routers.tarot import router as tarot_router
from app.routers.tarot_chat import router as tarot_chat_router

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


@app.get("/api/config")
def api_config() -> dict:
    """화면이 서버와 같은 값을 쓰도록 내려준다.

    채팅 질문 한도 같은 숫자를 프론트에 하드코딩하면 서버만 바꿨을 때
    안내 문구와 실제 동작이 어긋난다. config.py 를 유일한 출처로 둔다.
    """
    return {"chat_question_limit": settings.chat_question_limit}


app.include_router(chat_router)
app.include_router(face_router)
app.include_router(tarot_router)
app.include_router(tarot_chat_router)
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
app.mount(
    "/mediapipe",
    StaticFiles(directory=DIST_DIR / "mediapipe"),
    name="mediapipe",
)
app.include_router(pages_router)
app.include_router(saju_router)
app.include_router(saju_chat_router)
