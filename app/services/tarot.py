"""카드 뽑기와 해석 생성.

리딩 요약(summary_text)은 규칙 기반이다. 뽑는 순간에 외부 API 를 기다리게 하고
싶지 않고, 요약은 카드 조합만으로도 충분히 말이 되기 때문이다. 결과 화면의 채팅만
DeepSeek 을 쓰고, 키가 없거나 호출이 실패하면 규칙 기반 답변으로 되돌아간다.

요약까지 LLM 으로 바꾸려면 draw_reading() 이 만든 결과를 그대로 프롬프트 컨텍스트로
쓰고 interpretation_source 를 llm 으로 바꾸면 된다.
"""

from __future__ import annotations

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.services.llm import LlmUnavailable, complete, is_enabled
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

logger = logging.getLogger(__name__)

# 대화가 길어져도 토큰과 응답 시간이 무한정 늘지 않게 최근 것만 넘긴다.
CHAT_HISTORY_LIMIT = 12

SYSTEM_PROMPT = """너는 타로 사이트 '묘한운세'의 고양이 상담사 '묘라'야.
아래 규칙을 지켜서 한국어로 답해.

- 다정하고 담백한 해요체로 3~4문장 안에 답한다.
- 반드시 아래에 주어진 카드와 자리, 정/역방향에 근거해서 말한다.
  주어지지 않은 카드를 지어내지 않는다.
- 단정하지 말고 가능성으로 말한다. 질문이 카드와 무관하면 솔직히 말하고
  카드가 짚어주는 쪽으로 이야기를 돌린다.
- 타로는 재미와 참고용이다. 의학, 법률, 투자에 대해 단정적인 조언이나
  진단을 하지 않고, 필요하면 전문가와 상의하도록 권한다.
- 목록이나 표를 쓰지 말고 이어지는 문장으로 답한다."""


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
            source=InterpretationSource.rule,
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


def rule_answer(reading: TarotReading, question: str) -> str:
    """LLM 을 못 쓸 때 쓰는 답변. 카드에서 바로 끌어오므로 실패할 일이 없다."""
    keywords = reading_keywords(reading)[:4]
    focus = reading.cards[-1]
    direction = "역방향" if focus.orientation is Orientation.reversed else "정방향"
    return (
        f"'{question}'에 대해서는 마지막 자리의 {focus.card.name_ko}({direction})을 눈여겨보면 좋아요. "
        f"{focus.card.meaning(focus.orientation, reading.topic)} "
        f"이번 리딩의 핵심어는 {_ieyo(', '.join(keywords))}"
    )


def reading_context(reading: TarotReading) -> str:
    """뽑힌 카드를 프롬프트에 넣을 형태로 편다."""
    labels = {p.position_no: p.label_ko for p in reading.spread.positions}
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
            f"- [{label}] {entry.card.name_ko}({direction}) / 키워드: {keywords} / 해석: {meaning}"
        )
    return "\n".join(lines)


def build_chat_messages(reading: TarotReading) -> list[dict[str, str]]:
    """reading.messages 의 마지막이 지금 답해야 할 사용자 질문이다."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": reading_context(reading)},
    ]
    history = sorted(reading.messages, key=lambda m: m.seq)[-CHAT_HISTORY_LIMIT:]
    messages.extend(
        {"role": message.role.value, "content": message.content}
        for message in history
        if message.role is not ChatRole.system
    )
    return messages


def answer_question(
    reading: TarotReading, question: str
) -> tuple[str, InterpretationSource]:
    """DeepSeek 으로 답하고, 안 되면 규칙 기반 답변으로 되돌아간다.

    채팅이 끊기는 것보다 덜 똑똑한 답이라도 나오는 편이 낫다. 어느 쪽으로 답했는지는
    두 번째 값으로 알려서 화면에 표시할 수 있게 한다.
    """
    if not reading.cards:
        return "아직 뽑힌 카드가 없어서 답을 드리기 어려워요.", InterpretationSource.rule

    if is_enabled():
        try:
            return complete(build_chat_messages(reading)), InterpretationSource.llm
        except LlmUnavailable as exc:
            logger.info("규칙 기반 답변으로 대체합니다: %s", exc)

    return rule_answer(reading, question), InterpretationSource.rule


def append_chat(
    session: Session,
    reading: TarotReading,
    role: ChatRole,
    content: str,
    source: InterpretationSource | None = None,
) -> TarotChatMessage:
    next_seq = max((m.seq for m in reading.messages), default=0) + 1
    message = TarotChatMessage(
        reading_id=reading.id, seq=next_seq, role=role, content=content, source=source
    )
    session.add(message)
    reading.messages.append(message)
    return message
