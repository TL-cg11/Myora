from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.auth import optional_user, question_limit_for
from app.models import AppUser
from app.db import check_db
from app.security_auth import SecurityAuthMiddleware, TokenAuthenticator, parse_token_hashes
from app.security_db import find_security_user
from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router
from app.routers.auth import router as auth_router
from app.routers.face import router as face_router
from app.routers.pages import DIST_DIR, router as pages_router
from app.routers.saju import router as saju_router
from app.routers.saju_chat import router as saju_chat_router
from app.routers.security_audit import router as security_audit_router
from app.routers.security_events import router as security_events_router
from app.routers.tarot import router as tarot_router
from app.routers.tarot_chat import router as tarot_chat_router
from app.kafka_logging import api_request_log_middleware, flush_was_logs

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    SecurityAuthMiddleware,
    authenticator=TokenAuthenticator(
        parse_token_hashes(settings.security_auth_token_hashes), find_security_user
    ),
)
app.middleware("http")(api_request_log_middleware)


@app.on_event("shutdown")
def shutdown_was_log_producer() -> None:
    flush_was_logs()


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
def api_config(user: AppUser | None = Depends(optional_user)) -> dict:
    """화면이 서버와 같은 값을 쓰도록 내려준다.

    채팅 질문 한도 같은 숫자를 프론트에 하드코딩하면 서버만 바꿨을 때
    안내 문구와 실제 동작이 어긋난다. config.py 를 유일한 출처로 둔다.
    관리자 계정으로 로그인한 요청에는 확장된 한도를 내려준다. 실제 채팅
    엔드포인트도 같은 question_limit_for()로 계산하므로 여기서만 늘려
    보여 주고 서버가 다르게 세는 일은 없다.
    """
    return {
        "chat_question_limit": question_limit_for(user),
        "ai_message_max_chars": settings.ai_message_max_chars,
    }


app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(auth_router)
app.include_router(face_router)
app.include_router(tarot_router)
app.include_router(tarot_chat_router)
app.include_router(security_audit_router)
app.include_router(security_events_router)
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
app.mount(
    "/mediapipe",
    StaticFiles(directory=DIST_DIR / "mediapipe"),
    name="mediapipe",
)
app.include_router(pages_router)
app.include_router(saju_router)
app.include_router(saju_chat_router)
