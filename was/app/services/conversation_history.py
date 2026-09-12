"""Read a member's saju, tarot, and face conversations through one contract."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import and_, case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.conversation_schemas import (
    ConversationDetailOut,
    ConversationMessageOut,
    ConversationPageOut,
    ConversationResultOut,
    ConversationService,
    ConversationSummaryOut,
)
from app.models import Reading, ReadingChatMessage, TarotChatMessage, TarotReading


def _is_completed(column):
    """검사 중인 임시 메시지(policy_version IS NULL)만 숨긴다.

    정책 버전 자체로는 거르지 않는다. AI 문맥 조립(app/routers/chat.py 등)은
    옛 정책 버전 답변이 새 대화에 섞이지 않도록 POLICY_VERSION과 정확히 같은
    것만 쓰지만, 여기는 사용자가 자기 대화를 그대로 다시 보는 화면이다. 정책
    버전이 올라갔다고 실제로 나눈 대화가 사라져 보이면 안 된다."""
    return column.is_not(None)


# 목록 정렬에서 서비스가 같은 순서로 늘어서게 하는 유일한 출처. 다른 곳에서
# 0/1/2를 다시 적지 않고 전부 여기서 값을 가져온다 — 그래야 한 곳만 고쳐도
# 정렬·검증·커서 디코딩이 같이 맞는다.
SERVICE_RANK: dict[str, int] = {"saju": 0, "tarot": 1, "face": 2}
_MIN_SERVICE_RANK = min(SERVICE_RANK.values())
_MAX_SERVICE_RANK = max(SERVICE_RANK.values())


def _encode_cursor(row) -> str:
    raw = json.dumps(
        [row.created_at.isoformat(), row.service_rank, row.reading_id],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        created_at, service_rank, reading_id = json.loads(raw)
        parsed = datetime.fromisoformat(created_at)
        if not _MIN_SERVICE_RANK <= int(service_rank) <= _MAX_SERVICE_RANK or int(reading_id) < 1:
            raise ValueError
        return parsed, int(service_rank), int(reading_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="올바르지 않은 대화 목록 커서예요.") from error


def list_user_conversations(
    session: Session,
    *,
    user_id: int,
    service: ConversationService | Literal["all"] = "all",
    limit: int = 20,
    cursor: str | None = None,
) -> ConversationPageOut:
    common_count = (
        select(func.count(ReadingChatMessage.id))
        .where(
            ReadingChatMessage.reading_id == Reading.id,
            _is_completed(ReadingChatMessage.policy_version),
        )
        .correlate(Reading)
        .scalar_subquery()
    )
    common_last = (
        select(func.max(ReadingChatMessage.created_at))
        .where(
            ReadingChatMessage.reading_id == Reading.id,
            _is_completed(ReadingChatMessage.policy_version),
        )
        .correlate(Reading)
        .scalar_subquery()
    )
    common_rank = case(
        (Reading.service == "saju", SERVICE_RANK["saju"]), else_=SERVICE_RANK["face"]
    )
    common = select(
        Reading.id.label("reading_id"),
        Reading.service.label("service"),
        common_rank.label("service_rank"),
        Reading.created_at.label("created_at"),
        Reading.summary_title.label("title"),
        Reading.summary_text.label("summary"),
        common_count.label("message_count"),
        common_last.label("last_message_at"),
    ).where(
        Reading.user_id == user_id,
        Reading.service.in_(("saju", "face")),
    )

    tarot_count = (
        select(func.count(TarotChatMessage.id))
        .where(
            TarotChatMessage.reading_id == TarotReading.id,
            _is_completed(TarotChatMessage.policy_version),
        )
        .correlate(TarotReading)
        .scalar_subquery()
    )
    tarot_last = (
        select(func.max(TarotChatMessage.created_at))
        .where(
            TarotChatMessage.reading_id == TarotReading.id,
            _is_completed(TarotChatMessage.policy_version),
        )
        .correlate(TarotReading)
        .scalar_subquery()
    )
    tarot = select(
        TarotReading.id.label("reading_id"),
        literal("tarot").label("service"),
        literal(SERVICE_RANK["tarot"]).label("service_rank"),
        TarotReading.created_at.label("created_at"),
        TarotReading.summary_title.label("title"),
        TarotReading.summary_text.label("summary"),
        tarot_count.label("message_count"),
        tarot_last.label("last_message_at"),
    ).where(TarotReading.user_id == user_id)

    if service in {"saju", "face"}:
        common = common.where(Reading.service == service)
    elif service == "tarot":
        common = common.where(literal(False))
    if service != "all" and service != "tarot":
        tarot = tarot.where(literal(False))

    combined = union_all(common, tarot).subquery()
    statement = select(combined)
    if cursor:
        created_at, service_rank, reading_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                combined.c.created_at < created_at,
                and_(
                    combined.c.created_at == created_at,
                    combined.c.service_rank > service_rank,
                ),
                and_(
                    combined.c.created_at == created_at,
                    combined.c.service_rank == service_rank,
                    combined.c.reading_id < reading_id,
                ),
            )
        )
    rows = list(session.execute(
        statement.order_by(
            combined.c.created_at.desc(),
            combined.c.service_rank.asc(),
            combined.c.reading_id.desc(),
        ).limit(limit + 1)
    ))
    page_rows = rows[:limit]
    items = [
        ConversationSummaryOut(
            service=row.service,
            reading_id=row.reading_id,
            created_at=row.created_at,
            result=ConversationResultOut(title=row.title, summary=row.summary),
            message_count=row.message_count,
            last_message_at=row.last_message_at,
        )
        for row in page_rows
    ]
    return ConversationPageOut(
        items=items,
        next_cursor=_encode_cursor(page_rows[-1]) if len(rows) > limit else None,
    )


def _messages(rows) -> list[ConversationMessageOut]:
    return [
        ConversationMessageOut(
            seq=row.seq,
            role=row.role.value if hasattr(row.role, "value") else row.role,
            content=row.content,
            source=row.source.value if hasattr(row.source, "value") else row.source,
            created_at=row.created_at,
        )
        for row in rows
    ]


def get_user_conversation(
    session: Session,
    *,
    user_id: int,
    service: ConversationService,
    reading_id: int,
) -> ConversationDetailOut:
    if service == "tarot":
        reading = session.scalar(select(TarotReading).where(
            TarotReading.id == reading_id,
            TarotReading.user_id == user_id,
        ))
        message_model = TarotChatMessage
    else:
        reading = session.scalar(select(Reading).where(
            Reading.id == reading_id,
            Reading.service == service,
            Reading.user_id == user_id,
        ))
        message_model = ReadingChatMessage
    if reading is None:
        raise HTTPException(status_code=404, detail="대화 기록을 찾을 수 없어요.")

    message_rows = list(session.scalars(
        select(message_model)
        .where(
            message_model.reading_id == reading_id,
            _is_completed(message_model.policy_version),
        )
        .order_by(message_model.seq)
    ))
    messages = _messages(message_rows)
    return ConversationDetailOut(
        service=service,
        reading_id=reading.id,
        created_at=reading.created_at,
        result=ConversationResultOut(
            title=reading.summary_title,
            summary=reading.summary_text,
        ),
        message_count=len(messages),
        last_message_at=messages[-1].created_at if messages else None,
        messages=messages,
    )
