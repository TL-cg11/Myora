"""타로 결과 DeepSeek 채팅 API."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.auth import optional_user
from app.db import get_session
from app.models import (
    ChatRole,
    AppUser,
    InterpretationSource,
    Orientation,
    TarotChatMessage,
    TarotReading,
    Topic,
)
from app.prompts import PERSONA
from app.services.guardrail import safe_answer
from app.prompts.guardrail import POLICY_VERSION
from app.schemas import ChatCreate, ChatOut
from app.kafka_logging import emit_chat_exchange_log

router = APIRouter(prefix="/api/tarot", tags=["tarot-chat"])
logger = logging.getLogger(__name__)

_TOPIC_LABEL = {
    Topic.general: "오늘의 흐름",
    Topic.love: "연애운",
    Topic.career: "직업운",
    Topic.money: "금전운",
    Topic.health: "건강운",
}


def _load_reading(session: Session, reading_id: int, guest_key: UUID, user: AppUser | None = None) -> TarotReading:
    """guest_key가 맞는 리딩만 내준다. 없거나 남의 것이면 똑같이 404."""
    # Lock an authorized parent while reserving a question-sequence slot.
    owner = TarotReading.user_id == user.id if user else (TarotReading.user_id.is_(None) & (TarotReading.guest_key == str(guest_key)))
    session.scalar(select(TarotReading.id).where(TarotReading.id == reading_id, owner).with_for_update())
    reading = session.scalar(
        select(TarotReading)
        .options(
            selectinload(TarotReading.cards),
            selectinload(TarotReading.messages),
            selectinload(TarotReading.spread),
        )
        .where(
            TarotReading.id == reading_id,
            TarotReading.user_id == user.id if user else (TarotReading.user_id.is_(None) & (TarotReading.guest_key == str(guest_key))),
        )
    )
    if reading is None:
        raise HTTPException(status_code=404, detail="리딩을 찾을 수 없어요.")
    return reading


def _reading_context(reading: TarotReading) -> str:
    labels = {position.position_no: position.label_ko for position in reading.spread.positions}
    lines = [
        f"스프레드: {reading.spread.name_ko} ({reading.spread.description})",
        f"주제: {_TOPIC_LABEL[reading.topic]}",
    ]
    if reading.question:
        lines.append(f"처음 적은 질문: {reading.question}")
    lines.append("뽑힌 카드:")
    for entry in reading.cards:
        label = labels.get(entry.position_no, f"{entry.position_no}번째")
        direction = "역방향" if entry.orientation is Orientation.reversed else "정방향"
        keywords = ", ".join(entry.card.keywords(entry.orientation))
        meaning = entry.card.meaning(entry.orientation, reading.topic)
        lines.append(
            f"- [{label}] {entry.card.name_ko}({direction}) / "
            f"키워드: {keywords} / 해석: {meaning}"
        )
    return "\n".join(lines)


def _append_chat(
    session: Session,
    reading: TarotReading,
    role: ChatRole,
    content: str,
    source: InterpretationSource | None = None,
) -> None:
    message = TarotChatMessage(
        reading_id=reading.id,
        seq=max((item.seq for item in reading.messages), default=0) + 1,
        role=role,
        content=content,
        source=source,
        policy_version=POLICY_VERSION,
    )
    session.add(message)
    reading.messages.append(message)


@router.post("/readings/{reading_id}/chat", response_model=ChatOut)
async def create_chat_message(
    reading_id: int,
    guest_key: UUID,
    payload: ChatCreate,
    session: Session = Depends(get_session),
    user: AppUser | None = Depends(optional_user),
) -> ChatOut:
    reading = _load_reading(session, reading_id, guest_key, user)
    asked = sum(message.role is ChatRole.user for message in reading.messages)
    if asked >= settings.chat_question_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI 질문 {settings.chat_question_limit}회를 모두 사용했어요.",
        )

    history = [{"role":m.role.value,"content":m.content} for m in sorted(reading.messages, key=lambda m:m.seq)
               if m.policy_version == POLICY_VERSION and m.role is not ChatRole.system][-settings.ai_history_limit:]
    pending = TarotChatMessage(
        reading_id=reading.id,
        seq=max((item.seq for item in reading.messages), default=0) + 1,
        role=ChatRole.user,
        content="[검사 중인 질문]",
        policy_version=None,
    )
    session.add(pending)
    reading.messages.append(pending)
    # 질문 자리를 먼저 예약해 동시 요청도 공통 횟수 제한을 넘지 못하게 한다.
    session.commit()

    result = await safe_answer('tarot', PERSONA['tarot'], _reading_context(reading), payload.message, history)
    answer = result.answer
    source = InterpretationSource.llm if result.generated else InterpretationSource.rule
    pending.content = result.question
    pending.policy_version = POLICY_VERSION
    _append_chat(session, reading, ChatRole.assistant, answer, source=source)
    session.commit()
    emit_chat_exchange_log(
        feature="tarot",
        question=result.question,
        answer=answer,
        guest_key=guest_key,
        reading_id=reading_id,
        generated=result.generated,
    )
    return ChatOut(
        answer=answer,
        source=source,
        messages=sorted((m for m in reading.messages if m.policy_version == POLICY_VERSION), key=lambda message: message.seq),
    )
