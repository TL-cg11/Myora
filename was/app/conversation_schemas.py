"""Public response contracts for a member's saved fortune conversations."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer


def _as_utc_isoformat(value: datetime) -> str:
    """DB의 datetime은 이 서비스 관례상 naive지만 항상 UTC다(app/auth.py의
    utc_now() 참고). 시간대 표기 없이 JSON으로 나가면 브라우저의 Date 파서가
    '내 로컬 시간'으로 잘못 해석해 실제보다 몇 시간 어긋나 보인다. 명시적으로
    UTC임을 붙인다."""
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc_isoformat, return_type=str)]


ConversationService = Literal["saju", "tarot", "face"]


class ConversationResultOut(BaseModel):
    title: str | None = None
    summary: str | None = None


class ConversationMessageOut(BaseModel):
    seq: int
    role: Literal["user", "assistant", "system"]
    content: str
    source: Literal["rule", "llm"] | None = None
    created_at: UtcDatetime


class ConversationSummaryOut(BaseModel):
    service: ConversationService
    reading_id: int
    created_at: UtcDatetime
    result: ConversationResultOut
    message_count: int = Field(ge=0)
    last_message_at: UtcDatetime | None = None


class ConversationPageOut(BaseModel):
    items: list[ConversationSummaryOut]
    next_cursor: str | None = None


class ConversationDetailOut(ConversationSummaryOut):
    messages: list[ConversationMessageOut]
