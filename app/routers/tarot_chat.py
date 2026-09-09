"""타로 결과 DeepSeek 채팅 API."""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
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
from app.prompts.tarot import SYSTEM_PROMPT
from app.kafka_logging import emit_ai_request_log
from app.schemas import ChatCreate, ChatOut

router = APIRouter(prefix="/api/tarot", tags=["tarot-chat"])
logger = logging.getLogger(__name__)

CHAT_HISTORY_LIMIT = 12
MAX_TOKENS = 500

_TOPIC_LABEL = {
    Topic.general: "오늘의 흐름",
    Topic.love: "연애운",
    Topic.career: "직업운",
    Topic.money: "금전운",
    Topic.health: "건강운",
}


def _has_batchim(word: str) -> bool:
    """한글 마지막 글자에 받침이 있는지 확인한다."""
    if not word:
        return False
    code = ord(word[-1])
    return 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0


def _ieyo(word: str) -> str:
    """받침에 맞춰 '이에요/예요'를 붙인다."""
    return f"{word}이에요" if _has_batchim(word) else f"{word}예요"


def _load_reading(session: Session, reading_id: int, guest_key: UUID, user: AppUser | None = None) -> TarotReading:
    """guest_key가 맞는 리딩만 내준다. 없거나 남의 것이면 똑같이 404."""
    reading = session.scalar(
        select(TarotReading)
        .options(
            selectinload(TarotReading.cards),
            selectinload(TarotReading.messages),
            selectinload(TarotReading.spread),
        )
        .where(
            TarotReading.id == reading_id,
            TarotReading.user_id == user.id if user else TarotReading.guest_key == str(guest_key),
        )
    )
    if reading is None:
        raise HTTPException(status_code=404, detail="리딩을 찾을 수 없어요.")
    return reading


def _reading_keywords(reading: TarotReading) -> list[str]:
    seen: list[str] = []
    for entry in reading.cards:
        for keyword in entry.card.keywords(entry.orientation):
            if keyword not in seen:
                seen.append(keyword)
    return seen


def _rule_answer(reading: TarotReading, question: str) -> str:
    """DeepSeek을 쓸 수 없을 때 카드에서 직접 만드는 답변."""
    if not reading.cards:
        return "아직 뽑힌 카드가 없어서 답을 드리기 어려워요."

    focus = reading.cards[-1]
    direction = "역방향" if focus.orientation is Orientation.reversed else "정방향"
    keywords = ", ".join(_reading_keywords(reading)[:4])
    return (
        f"'{question}'에 대해서는 마지막 자리의 {focus.card.name_ko}({direction})을 "
        f"눈여겨보면 좋아요. {focus.card.meaning(focus.orientation, reading.topic)} "
        f"이번 리딩의 핵심어는 {_ieyo(keywords)}."
    )


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


def _deepseek_messages(reading: TarotReading) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _reading_context(reading)},
    ]
    history = sorted(reading.messages, key=lambda message: message.seq)[
        -CHAT_HISTORY_LIMIT:
    ]
    messages.extend(
        {"role": message.role.value, "content": message.content}
        for message in history
        if message.role is not ChatRole.system
    )
    return messages


async def _deepseek_answer(reading: TarotReading) -> str:
    payload = {
        "model": settings.deepseek_tarot_model,
        "messages": _deepseek_messages(reading),
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_tarot_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

    try:
        timeout = httpx.Timeout(settings.llm_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
        if not answer:
            raise ValueError("DeepSeek returned an empty answer")
        return answer
    except (httpx.HTTPError, KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
        logger.warning("DeepSeek 타로 요청 실패: %s", type(error).__name__)
        raise RuntimeError("타로 AI 응답을 가져오지 못했습니다.") from error


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

    _append_chat(session, reading, ChatRole.user, payload.message)
    source = InterpretationSource.rule
    answer = _rule_answer(reading, payload.message)
    if settings.tarot_llm_enabled:
        try:
            emit_ai_request_log(
                feature="tarot",
                question=payload.message,
                model=settings.deepseek_tarot_model,
                timeout_seconds=settings.llm_timeout,
                guest_key=guest_key,
                reading_id=reading_id,
                question_sequence=asked + 1,
                message_count=len(_deepseek_messages(reading)),
                context_length=len(_reading_context(reading)),
            )
            answer = await _deepseek_answer(reading)
            source = InterpretationSource.llm
        except RuntimeError:
            logger.info("DeepSeek 실패로 규칙 기반 타로 답변을 사용합니다.")

    _append_chat(session, reading, ChatRole.assistant, answer, source=source)
    session.commit()
    return ChatOut(
        answer=answer,
        source=source,
        messages=sorted(reading.messages, key=lambda message: message.seq),
    )
