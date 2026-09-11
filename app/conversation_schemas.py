"""Public response contracts for a member's saved fortune conversations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ConversationService = Literal["saju", "tarot", "face"]


class ConversationResultOut(BaseModel):
    title: str | None = None
    summary: str | None = None


class ConversationMessageOut(BaseModel):
    seq: int
    role: Literal["user", "assistant", "system"]
    content: str
    source: Literal["rule", "llm"] | None = None
    created_at: datetime


class ConversationSummaryOut(BaseModel):
    service: ConversationService
    reading_id: int
    created_at: datetime
    result: ConversationResultOut
    message_count: int = Field(ge=0)
    last_message_at: datetime | None = None


class ConversationPageOut(BaseModel):
    items: list[ConversationSummaryOut]
    next_cursor: str | None = None


class ConversationDetailOut(ConversationSummaryOut):
    messages: list[ConversationMessageOut]
