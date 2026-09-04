"""타로 API 요청/응답 스키마."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
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


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    content: str
    source: InterpretationSource | None = None
    created_at: datetime


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
    messages: list[ChatMessageOut] = []


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




class ChatCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatOut(BaseModel):
    answer: str
    # 이번 답변을 무엇으로 만들었는지. 리딩 요약의 출처와는 별개다.
    source: InterpretationSource
    messages: list[ChatMessageOut]


FaceMood = Literal["차분한", "밝은", "신비로운", "단단한"]


class FaceMeasurementsIn(BaseModel):
    """브라우저에서 계산한 비율만 받는다. 사진·랜드마크 필드는 허용하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    aspect_ratio: float = Field(gt=0.5, lt=2.5)
    jaw_ratio: float = Field(gt=0, lt=1.5)
    forehead_ratio: float = Field(gt=0, lt=1.5)
    eye_ratio: float = Field(gt=0, lt=1)
    mouth_ratio: float = Field(gt=0, lt=1)
    symmetry_score: float = Field(ge=0, le=1)
    coverage: float | None = Field(default=None, ge=0, le=1)
    roll_degrees: float | None = Field(default=None, ge=0, lt=180)
    nose_offset: float | None = Field(default=None, ge=0, le=1)


class FaceReadingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_key: UUID
    mood: FaceMood
    detector_version: str = Field(min_length=1, max_length=32)
    # 구버전 브라우저와의 호환용으로만 받으며 서버는 이 값을 사용하지 않는다.
    summary_text: str | None = Field(default=None, max_length=8_000)
    measurements: FaceMeasurementsIn


class FaceReadingOut(BaseModel):
    id: int
    shape_code: str
    summary_title: str
    summary_text: str
    mood: str | None
    created_at: datetime
    keywords: list[str] = Field(default_factory=list)
