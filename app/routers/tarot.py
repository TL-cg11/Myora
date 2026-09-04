"""타로 카드·스프레드·리딩 API."""

from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import (
    ChatRole,
    InterpretationSource,
    Orientation,
    ReadingStatus,
    TarotCard,
    TarotChatMessage,
    TarotReading,
    TarotReadingCard,
    TarotSpread,
    Topic,
)
from app.schemas import (
    CardOut,
    ChatMessageOut,
    ReadingCardOut,
    ReadingCreate,
    ReadingOut,
    ReadingSummaryOut,
    SpreadOut,
)
router = APIRouter(prefix="/api/tarot", tags=["tarot"])

HISTORY_LIMIT = 12
REVERSED_RATE = 0.5
_rng = secrets.SystemRandom()

_TOPIC_LABEL = {
    Topic.general: "오늘의 흐름",
    Topic.love: "연애운",
    Topic.career: "직업운",
    Topic.money: "금전운",
    Topic.health: "건강운",
}


def get_spread(session: Session, code: str) -> TarotSpread | None:
    return session.scalar(
        select(TarotSpread)
        .options(selectinload(TarotSpread.positions))
        .where(TarotSpread.code == code, TarotSpread.is_active.is_(True))
    )


def get_spreads(session: Session) -> list[TarotSpread]:
    return list(
        session.scalars(
            select(TarotSpread)
            .options(selectinload(TarotSpread.positions))
            .where(TarotSpread.is_active.is_(True))
            .order_by(TarotSpread.sort_order)
        )
    )


def compose_interpretation(reading: TarotReading) -> tuple[str, str]:
    """뽑힌 카드의 자리별 해석을 이어 붙여 요약을 만든다."""
    labels = {position.position_no: position.label_ko for position in reading.spread.positions}
    lines = []
    for entry in reading.cards:
        label = labels.get(entry.position_no, f"{entry.position_no}번째")
        direction = "역방향" if entry.orientation is Orientation.reversed else "정방향"
        meaning = entry.card.meaning(entry.orientation, reading.topic)
        lines.append(f"{label}의 {entry.card.name_ko}({direction})은 {meaning}")

    return f"카드가 전하는 {_TOPIC_LABEL[reading.topic]} 이야기", " ".join(lines)


def draw_reading(
    session: Session,
    *,
    spread: TarotSpread,
    guest_key: str,
    topic: Topic,
    question: str | None,
) -> TarotReading:
    """서버에서 카드를 뽑고 규칙 기반 요약과 첫 인사를 저장한다."""
    deck = list(session.scalars(select(TarotCard).where(TarotCard.is_active.is_(True))))
    if len(deck) < spread.card_count:
        raise ValueError(
            f"카드가 부족해요. 필요 {spread.card_count}장, 사용 가능 {len(deck)}장"
        )

    reading = TarotReading(
        guest_key=guest_key,
        spread_id=spread.id,
        topic=topic,
        question=question,
        status=ReadingStatus.drawn,
    )
    session.add(reading)
    session.flush()

    for position, card in enumerate(_rng.sample(deck, spread.card_count), start=1):
        reading.cards.append(
            TarotReadingCard(
                position_no=position,
                card_id=card.id,
                orientation=(
                    Orientation.reversed
                    if _rng.random() < REVERSED_RATE
                    else Orientation.upright
                ),
            )
        )
    session.flush()

    reading.summary_title, reading.summary_text = compose_interpretation(reading)
    reading.interpretation_source = InterpretationSource.rule
    reading.status = ReadingStatus.interpreted
    session.add(
        TarotChatMessage(
            reading_id=reading.id,
            seq=1,
            role=ChatRole.assistant,
            content="결과를 함께 보고 있어요. 더 궁금한 점을 편하게 물어보세요!",
            source=InterpretationSource.rule,
        )
    )
    session.commit()
    return reading


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
    return [SpreadOut.model_validate(item) for item in get_spreads(session)]


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
    spread = get_spread(session, payload.spread_code)
    if spread is None:
        raise HTTPException(status_code=404, detail="스프레드를 찾을 수 없어요.")

    try:
        reading = draw_reading(
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
