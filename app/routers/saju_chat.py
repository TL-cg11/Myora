from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth import optional_user
from app.db import get_session
from app.models import AppUser
from app.prompts.saju import SAJU_PERSONA
from app.routers.chat import ChatRequest, ChatResponse, reading_chat

router = APIRouter(prefix='/api/saju', tags=['saju-chat'])

@router.post('/chat', response_model=ChatResponse)
async def saju_chat(request: ChatRequest, session: Session = Depends(get_session), user: AppUser | None = Depends(optional_user)):
    return await reading_chat('saju', SAJU_PERSONA, request, session, user)
