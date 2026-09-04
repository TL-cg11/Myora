"""타로 API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import ChatRole, TarotCard, TarotReading
from app.schemas import (
    CardOut,
    ChatCreate,
    ChatMessageOut,
    ChatOut,
    ReadingCardOut,
    ReadingCreate,
    ReadingOut,
    ReadingSummaryOut,
    SpreadOut,
)
from app.services import tarot as service

router = APIRouter(prefix="/api/tarot", tags=["tarot"])

HISTORY_LIMIT = 12

# 결과 화면 채팅에서 물어볼 수 있는 횟수. 관상(app/routers/chat.py)과 같은 5회다.
# 화면의 src/pages/tarot/TarotPage.jsx QUESTION_LIMIT 과 같은 값을 써야 한다.
QUESTION_LIMIT = 5


def _load_reading(session: Session, reading_id: int, guest_key: UUID) -> TarotReading:
    """guest_key가 맞는 리딩만 내준다. 없거나 남의 것이면 똑같이 404."""
    reading = session.scalar(
        select(TarotReading)
        .options(
            selectinload(TarotReading.cards),
            selectinload(TarotReading.messages),
            selectinload(TarotReading.spread),
        )
        .where(TarotReading.id == reading_id, TarotReading.guest_key == str(guest_key))
    )
    if reading is None:
        raise HTTPException(status_code=404, detail="리딩을 찾을 수 없어요.")
    return reading


def _to_reading_out(reading: TarotReading) -> ReadingOut:
    positions = {p.position_no: p for p in reading.spread.positions}
    return ReadingOut(
        id=reading.id,
        spread=SpreadOut.model_validate(reading.spread),
        topic=reading.topic,
        question=reading.question,
        summary_title=reading.summary_title,
        summary_text=reading.summary_text,
        interpretation_source=reading.interpretation_source,
        status=reading.status,
        created_at=reading.created_at,
        messages=[
            ChatMessageOut.model_validate(message)
            for message in sorted(reading.messages, key=lambda m: m.seq)
        ],
        cards=[
            ReadingCardOut(
                position_no=entry.position_no,
                label_ko=(
                    positions[entry.position_no].label_ko
                    if entry.position_no in positions
                    else f"{entry.position_no}번째"
                ),
                position_description=(
                    positions[entry.position_no].description
                    if entry.position_no in positions
                    else None
                ),
                card=CardOut.model_validate(entry.card),
                orientation=entry.orientation,
                keywords=entry.card.keywords(entry.orientation),
                meaning=entry.card.meaning(entry.orientation, reading.topic),
            )
            for entry in reading.cards
        ],
    )


@router.get("/spreads", response_model=list[SpreadOut])
def list_spreads(session: Session = Depends(get_session)) -> list[SpreadOut]:
    return [SpreadOut.model_validate(item) for item in service.list_spreads(session)]


@router.get("/cards", response_model=list[CardOut])
def list_cards(session: Session = Depends(get_session)) -> list[CardOut]:
    cards = session.scalars(
        select(TarotCard).where(TarotCard.is_active.is_(True)).order_by(TarotCard.id)
    )
    return [CardOut.model_validate(card) for card in cards]


@router.post("/readings", response_model=ReadingOut, status_code=status.HTTP_201_CREATED)
def create_reading(
    payload: ReadingCreate, session: Session = Depends(get_session)
) -> ReadingOut:
    spread = service.get_spread(session, payload.spread_code)
    if spread is None:
        raise HTTPException(status_code=404, detail="스프레드를 찾을 수 없어요.")

    try:
        reading = service.draw_reading(
            session,
            spread=spread,
            guest_key=str(payload.guest_key),
            topic=payload.topic,
            question=payload.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _to_reading_out(reading)


@router.get("/readings", response_model=list[ReadingSummaryOut])
def list_readings(
    guest_key: UUID,
    limit: int = Query(default=HISTORY_LIMIT, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[ReadingSummaryOut]:
    readings = session.scalars(
        select(TarotReading)
        .options(selectinload(TarotReading.cards), selectinload(TarotReading.spread))
        .where(TarotReading.guest_key == str(guest_key))
        .order_by(TarotReading.created_at.desc(), TarotReading.id.desc())
        .limit(limit)
    )
    return [
        ReadingSummaryOut(
            id=reading.id,
            spread_name=reading.spread.name_ko,
            topic=reading.topic,
            summary_title=reading.summary_title,
            card_names=[entry.card.name_ko for entry in reading.cards],
            created_at=reading.created_at,
        )
        for reading in readings
    ]


@router.get("/readings/{reading_id}", response_model=ReadingOut)
def get_reading(
    reading_id: int, guest_key: UUID, session: Session = Depends(get_session)
) -> ReadingOut:
    return _to_reading_out(_load_reading(session, reading_id, guest_key))


@router.post("/readings/{reading_id}/chat", response_model=ChatOut)
def create_chat_message(
    reading_id: int,
    guest_key: UUID,
    payload: ChatCreate,
    session: Session = Depends(get_session),
) -> ChatOut:
    reading = _load_reading(session, reading_id, guest_key)

    # 화면에서도 막지만 서버가 실제 기준이다. 대화가 DB 에 있으므로 저장된 질문을
    # 세면 되고, 새로고침하거나 API 를 직접 호출해도 같은 한도가 적용된다.
    asked = sum(1 for message in reading.messages if message.role is ChatRole.user)
    if asked >= QUESTION_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI 질문 {QUESTION_LIMIT}회를 모두 사용했어요.",
        )

    # 질문을 먼저 넣어야 LLM 에 넘길 대화 기록의 마지막이 이번 질문이 된다.
    service.append_chat(session, reading, ChatRole.user, payload.message)
    answer, source = service.answer_question(reading, payload.message)
    service.append_chat(session, reading, ChatRole.assistant, answer, source=source)
    session.commit()

    # source 는 리딩 요약이 아니라 이번 답변을 무엇으로 만들었는지를 가리킨다.
    return ChatOut(
        answer=answer,
        source=source,
        messages=sorted(reading.messages, key=lambda m: m.seq),
    )
