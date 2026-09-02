"""타로 API 요청/응답 스키마."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import InterpretationSource, Orientation, ReadingStatus, Topic


class SpreadPositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_no: int
    label_ko: str
    description: str | None = None


class SpreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name_ko: str
    description: str
    card_count: int
    positions: list[SpreadPositionOut] = []


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name_ko: str
    name_en: str
    image_path: str | None = None


class ReadingCardOut(BaseModel):
    position_no: int
    label_ko: str
    position_description: str | None = None
    card: CardOut
    orientation: Orientation
    keywords: list[str]
    meaning: str


class ReadingOut(BaseModel):
    id: int
    spread: SpreadOut
    topic: Topic
    question: str | None
    summary_title: str | None
    summary_text: str | None
    interpretation_source: InterpretationSource
    status: ReadingStatus
    created_at: datetime
    cards: list[ReadingCardOut]


class ReadingSummaryOut(BaseModel):
    """마이페이지 히스토리용 축약 응답."""

    id: int
    spread_name: str
    topic: Topic
    summary_title: str | None
    card_names: list[str]
    created_at: datetime


class ReadingCreate(BaseModel):
    # user_id는 받지 않는다. 인증이 붙기 전까지 클라이언트가 보낸 회원 식별자를
    # 그대로 신뢰하면 남의 기록을 조작할 수 있다.
    spread_code: str = Field(min_length=1, max_length=32)
    topic: Topic = Topic.general
    question: str | None = Field(default=None, max_length=255)
    guest_key: UUID


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    content: str
    created_at: datetime


class ChatCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatOut(BaseModel):
    answer: str
    source: InterpretationSource
    messages: list[ChatMessageOut]
