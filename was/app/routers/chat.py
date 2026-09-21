from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import optional_user, question_limit_for
from app.db import get_session
from app.models import AppUser, ReadingChatMessage
from app.prompts import PERSONA
from app.prompts.guardrail import POLICY_VERSION
from app.services.chat_context import load_context
from app.services.guardrail import safe_answer
from app.kafka_logging import emit_chat_exchange_log

router = APIRouter(prefix='/api', tags=['chat'])

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reading_id: int = Field(gt=0)
    guest_key: UUID
    message: str = Field(min_length=1, max_length=settings.ai_message_max_chars)

class ChatResponse(BaseModel):
    answer: str
    questions_used: int

async def reading_chat(service, persona, request, session, user):
    context = load_context(session, service, request.reading_id, request.guest_key, user)
    rows = list(session.scalars(select(ReadingChatMessage).where(ReadingChatMessage.reading_id == request.reading_id).order_by(ReadingChatMessage.seq)))
    asked = sum(row.role == 'user' for row in rows)
    limit = question_limit_for(user)
    if asked >= limit:
        raise HTTPException(429, f'AI 질문 {limit}회를 모두 사용했어요.')
    history = [{'role':r.role,'content':r.content} for r in rows if r.policy_version == POLICY_VERSION][-settings.ai_history_limit:]
    seq = max((r.seq for r in rows), default=0)
    pending = ReadingChatMessage(
        reading_id=request.reading_id,
        seq=seq + 1,
        role='user',
        content=request.message,
        policy_version=None,
    )
    session.add(pending)
    # 질문 자리를 먼저 예약해 동시 요청도 공통 횟수 제한을 넘지 못하게 한다.
    session.commit()

    result = await safe_answer(service, persona, context, request.message, history)
    pending.content = request.message
    pending.policy_version = POLICY_VERSION
    session.add(
        ReadingChatMessage(
            reading_id=request.reading_id,
            seq=seq + 2,
            role='assistant',
            content=result.answer,
            policy_version=POLICY_VERSION,
            source='llm' if result.generated else 'rule',
        )
    )
    session.commit()
    emit_chat_exchange_log(
        feature=service,
        question=request.message,
        answer=result.answer,
        guest_key=request.guest_key,
        reading_id=request.reading_id,
        generated=result.generated,
    )
    return ChatResponse(answer=result.answer, questions_used=asked+1)

@router.post('/face/chat', response_model=ChatResponse)
async def chat(request: ChatRequest, session: Session = Depends(get_session), user: AppUser | None = Depends(optional_user)):
    return await reading_chat('face', PERSONA['face'], request, session, user)
