"""카드 뽑기와 해석 생성.

해석은 현재 규칙 기반이다. LLM을 붙이면 draw_reading()이 만든 결과를 그대로
프롬프트 컨텍스트로 쓰고 interpretation_source만 llm으로 바꾸면 된다.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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

# 역방향이 나올 확률. 실제 타로와 같은 5:5이며 톤을 바꾸려면 이 값만 조정한다.
REVERSED_RATE = 0.5

_rng = secrets.SystemRandom()

def _has_batchim(word: str) -> bool:
    """한글 마지막 글자에 받침이 있는지."""
    if not word:
        return False
    code = ord(word[-1])
    if not 0xAC00 <= code <= 0xD7A3:
        return False
    return (code - 0xAC00) % 28 != 0


def _ieyo(word: str) -> str:
    """받침에 맞는 종결 어미를 붙인다. 전환 → 전환이에요, 자유 → 자유예요."""
    return f"{word}이에요" if _has_batchim(word) else f"{word}예요"


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


def list_spreads(session: Session) -> list[TarotSpread]:
    return list(
        session.scalars(
            select(TarotSpread)
            .options(selectinload(TarotSpread.positions))
            .where(TarotSpread.is_active.is_(True))
            .order_by(TarotSpread.sort_order)
        )
    )


def draw_reading(
    session: Session,
    *,
    spread: TarotSpread,
    guest_key: str,
    topic: Topic,
    question: str | None,
) -> TarotReading:
    """스프레드 자리 수만큼 서로 다른 카드를 뽑아 리딩을 저장한다.

    셔플은 서버에서만 한다. 클라이언트가 카드를 고르는 UI라도 실제로 어떤 카드가
    나왔는지는 서버가 정해야 결과를 조작할 수 없다.
    """
    deck = list(session.scalars(select(TarotCard).where(TarotCard.is_active.is_(True))))
    if len(deck) < spread.card_count:
        raise ValueError(
            f"카드가 부족해요. 필요 {spread.card_count}장, 사용 가능 {len(deck)}장"
        )

    picked = _rng.sample(deck, spread.card_count)
    reading = TarotReading(
        guest_key=guest_key,
        spread_id=spread.id,
        topic=topic,
        question=question,
        status=ReadingStatus.drawn,
    )
    session.add(reading)
    session.flush()

    for index, card in enumerate(picked, start=1):
        reading.cards.append(
            TarotReadingCard(
                position_no=index,
                card_id=card.id,
                orientation=(
                    Orientation.reversed
                    if _rng.random() < REVERSED_RATE
                    else Orientation.upright
                ),
            )
        )
    session.flush()

    title, text = compose_interpretation(reading)
    reading.summary_title = title
    reading.summary_text = text
    reading.interpretation_source = InterpretationSource.rule
    reading.status = ReadingStatus.interpreted

    session.add(
        TarotChatMessage(
            reading_id=reading.id,
            seq=1,
            role=ChatRole.assistant,
            content="결과를 함께 보고 있어요. 더 궁금한 점을 편하게 물어보세요!",
        )
    )
    session.commit()
    return reading


def compose_interpretation(reading: TarotReading) -> tuple[str, str]:
    """뽑힌 카드의 자리별 해석을 이어 붙여 요약을 만든다."""
    labels = {p.position_no: p.label_ko for p in reading.spread.positions}
    lines = []
    for entry in reading.cards:
        label = labels.get(entry.position_no, f"{entry.position_no}번째")
        direction = "역방향" if entry.orientation is Orientation.reversed else "정방향"
        meaning = entry.card.meaning(entry.orientation, reading.topic)
        lines.append(f"{label}의 {entry.card.name_ko}({direction})은 {meaning}")

    title = f"카드가 전하는 {_TOPIC_LABEL[reading.topic]} 이야기"
    return title, " ".join(lines)


def reading_keywords(reading: TarotReading) -> list[str]:
    seen: list[str] = []
    for entry in reading.cards:
        for keyword in entry.card.keywords(entry.orientation):
            if keyword not in seen:
                seen.append(keyword)
    return seen


def answer_question(reading: TarotReading, question: str) -> str:
    """LLM이 붙기 전까지 쓰는 규칙 기반 답변."""
    keywords = reading_keywords(reading)[:4]
    focus = reading.cards[-1] if reading.cards else None
    if focus is None:
        return "아직 뽑힌 카드가 없어서 답을 드리기 어려워요."

    direction = "역방향" if focus.orientation is Orientation.reversed else "정방향"
    return (
        f"'{question}'에 대해서는 마지막 자리의 {focus.card.name_ko}({direction})을 눈여겨보면 좋아요. "
        f"{focus.card.meaning(focus.orientation, reading.topic)} "
        f"이번 리딩의 핵심어는 {_ieyo(', '.join(keywords))}"
    )


def append_chat(
    session: Session, reading: TarotReading, role: ChatRole, content: str
) -> TarotChatMessage:
    next_seq = max((m.seq for m in reading.messages), default=0) + 1
    message = TarotChatMessage(
        reading_id=reading.id, seq=next_seq, role=role, content=content
    )
    session.add(message)
    reading.messages.append(message)
    return message
