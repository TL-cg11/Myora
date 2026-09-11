"""운세 도메인 ORM 모델.

테이블 정의의 원본은 luck-mariadb의 sql/init/02_tarot.sql이다. 이 모델은 그 스키마를
그대로 반영하며, 스키마를 바꿀 때는 SQL 쪽을 먼저 고친다(앱 계정에 DDL 권한이 없다).
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Arcana(str, enum.Enum):
    major = "major"
    minor = "minor"


class Suit(str, enum.Enum):
    wands = "wands"
    cups = "cups"
    swords = "swords"
    pentacles = "pentacles"


class Orientation(str, enum.Enum):
    upright = "upright"
    reversed = "reversed"


class Topic(str, enum.Enum):
    general = "general"
    love = "love"
    career = "career"
    money = "money"
    health = "health"


class MeaningTopic(str, enum.Enum):
    """tarot_card_meaning은 general을 갖지 않는다(general은 카드의 기본 해석)."""

    love = "love"
    career = "career"
    money = "money"
    health = "health"


class InterpretationSource(str, enum.Enum):
    rule = "rule"
    llm = "llm"


class ReadingStatus(str, enum.Enum):
    drawn = "drawn"
    interpreted = "interpreted"
    failed = "failed"


def _enum(python_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(python_enum, name=name, values_callable=lambda e: [m.value for m in e])


class AppUserRole(str, enum.Enum):
    """가입 계정의 권한 등급. 게스트는 별도 개념이라 여기 포함하지 않는다."""

    user = "user"
    admin = "admin"


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(40))
    email: Mapped[str] = mapped_column(String(190), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(12), default="active")
    role: Mapped[AppUserRole] = mapped_column(
        _enum(AppUserRole, "app_user_role"), default=AppUserRole.user
    )
    failed_login_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def is_admin(self) -> bool:
        return self.role == AppUserRole.admin


class AuthSession(Base):
    __tablename__ = "auth_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[AppUser] = relationship(lazy="joined")


class ChatRole(str, enum.Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class TarotCard(Base):
    __tablename__ = "tarot_card"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    arcana: Mapped[Arcana] = mapped_column(_enum(Arcana, "arcana"))
    suit: Mapped[Suit | None] = mapped_column(_enum(Suit, "suit"), nullable=True)
    number: Mapped[int] = mapped_column(Integer)
    name_ko: Mapped[str] = mapped_column(String(40))
    name_en: Mapped[str] = mapped_column(String(40))
    keyword_upright: Mapped[str] = mapped_column(String(120))
    keyword_reversed: Mapped[str] = mapped_column(String(120))
    meaning_upright: Mapped[str] = mapped_column(String(500))
    meaning_reversed: Mapped[str] = mapped_column(String(500))
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    meanings: Mapped[list["TarotCardMeaning"]] = relationship(back_populates="card")

    def keywords(self, orientation: Orientation) -> list[str]:
        raw = self.keyword_upright if orientation is Orientation.upright else self.keyword_reversed
        return [item.strip() for item in raw.split(",") if item.strip()]

    def meaning(self, orientation: Orientation, topic: Topic) -> str:
        """주제별 해석이 있으면 그것을, 없으면 카드의 기본 해석을 쓴다."""
        for item in self.meanings:
            if item.topic.value == topic.value and item.orientation is orientation:
                return item.meaning
        return self.meaning_upright if orientation is Orientation.upright else self.meaning_reversed


class TarotCardMeaning(Base):
    __tablename__ = "tarot_card_meaning"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_card.id", ondelete="CASCADE"))
    topic: Mapped[MeaningTopic] = mapped_column(_enum(MeaningTopic, "meaning_topic"))
    orientation: Mapped[Orientation] = mapped_column(_enum(Orientation, "orientation"))
    meaning: Mapped[str] = mapped_column(String(500))

    card: Mapped[TarotCard] = relationship(back_populates="meanings")


class TarotSpread(Base):
    __tablename__ = "tarot_spread"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name_ko: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(255))
    card_count: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    positions: Mapped[list["TarotSpreadPosition"]] = relationship(
        back_populates="spread", order_by="TarotSpreadPosition.position_no"
    )


class TarotSpreadPosition(Base):
    __tablename__ = "tarot_spread_position"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    spread_id: Mapped[int] = mapped_column(ForeignKey("tarot_spread.id", ondelete="CASCADE"))
    position_no: Mapped[int] = mapped_column(Integer)
    label_ko: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    spread: Mapped[TarotSpread] = relationship(back_populates="positions")


class TarotReading(Base):
    __tablename__ = "tarot_reading"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True)
    guest_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    spread_id: Mapped[int] = mapped_column(ForeignKey("tarot_spread.id"))
    topic: Mapped[Topic] = mapped_column(_enum(Topic, "topic"), default=Topic.general)
    question: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation_source: Mapped[InterpretationSource] = mapped_column(
        _enum(InterpretationSource, "interpretation_source"), default=InterpretationSource.rule
    )
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ReadingStatus] = mapped_column(
        _enum(ReadingStatus, "reading_status"), default=ReadingStatus.drawn
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    spread: Mapped[TarotSpread] = relationship(lazy="joined")
    cards: Mapped[list["TarotReadingCard"]] = relationship(
        back_populates="reading",
        order_by="TarotReadingCard.position_no",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list["TarotChatMessage"]] = relationship(
        back_populates="reading",
        order_by="TarotChatMessage.seq",
        cascade="all, delete-orphan",
    )


class TarotReadingCard(Base):
    __tablename__ = "tarot_reading_card"

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_id: Mapped[int] = mapped_column(ForeignKey("tarot_reading.id", ondelete="CASCADE"))
    position_no: Mapped[int] = mapped_column(Integer)
    card_id: Mapped[int] = mapped_column(ForeignKey("tarot_card.id"))
    orientation: Mapped[Orientation] = mapped_column(
        _enum(Orientation, "orientation"), default=Orientation.upright
    )

    reading: Mapped[TarotReading] = relationship(back_populates="cards")
    card: Mapped[TarotCard] = relationship(lazy="joined")


class TarotChatMessage(Base):
    __tablename__ = "tarot_chat_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    reading_id: Mapped[int] = mapped_column(ForeignKey("tarot_reading.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    role: Mapped[ChatRole] = mapped_column(_enum(ChatRole, "chat_role"))
    content: Mapped[str] = mapped_column(Text)
    # assistant 답변을 무엇으로 만들었는지. user/system 메시지는 NULL 이다.
    source: Mapped[InterpretationSource | None] = mapped_column(
        _enum(InterpretationSource, "interpretation_source"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    policy_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    reading: Mapped[TarotReading] = relationship(back_populates="messages")


class Reading(Base):
    """사주·관상·타로가 공유하는 리딩 목록의 뼈대."""

    __tablename__ = "reading"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    service: Mapped[str] = mapped_column(String(10))
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guest_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation_source: Mapped[str] = mapped_column(String(8), default="rule")
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SajuChart(Base):
    __tablename__ = "saju_chart"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    birth_date: Mapped[date] = mapped_column(Date)
    birth_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    time_unknown: Mapped[bool] = mapped_column(Boolean, default=False)
    gender: Mapped[str] = mapped_column(String(10))
    engine_version: Mapped[str] = mapped_column(String(32))
    pillar_year: Mapped[str] = mapped_column(String(2))
    pillar_month: Mapped[str] = mapped_column(String(2))
    pillar_day: Mapped[str] = mapped_column(String(2))
    pillar_hour: Mapped[str | None] = mapped_column(String(2), nullable=True)
    jeonggyeok: Mapped[str | None] = mapped_column(String(40), nullable=True)
    yongsin: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sinsal: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SajuReading(Base):
    __tablename__ = "saju_reading"

    reading_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reading.id", ondelete="CASCADE"), primary_key=True
    )
    chart_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("saju_chart.id"))
    birth_profile_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    topic: Mapped[str] = mapped_column(String(10), default="general")
    question: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SajuTerm(Base):
    """사주 계산값(분류 + 한자)으로 조회하는 한글 뜻 사전."""

    __tablename__ = "saju_term"
    __table_args__ = (UniqueConstraint("category", "hanja", name="uk_saju_term"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(24))
    hanja: Mapped[str] = mapped_column(String(16))
    name_ko: Mapped[str] = mapped_column(String(40))
    meaning_ko: Mapped[str] = mapped_column(Text)


class SajuNarrativeRule(Base):
    """일주별 상담 프로필과 계산 결과에 따라 선택할 보완 문구."""

    __tablename__ = "saju_narrative_rule"
    __table_args__ = (UniqueConstraint("category", "hanja", name="uk_saju_narrative_rule"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(24))
    hanja: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)


class FaceShape(Base):
    __tablename__ = "face_shape"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(80))
    keyword: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FaceInterpretation(Base):
    """측정 구간별 관상 설명 기준 데이터."""

    __tablename__ = "face_interpretation"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    category: Mapped[str] = mapped_column(String(24))
    code: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500))
    keyword: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FaceReading(Base):
    """사진과 랜드마크 원본을 제외한 관상 측정값."""

    __tablename__ = "face_reading"

    reading_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reading.id", ondelete="CASCADE"), primary_key=True
    )
    shape_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("face_shape.id"), nullable=True
    )
    aspect_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    jaw_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    forehead_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    eye_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    mouth_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    symmetry_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    mood: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detector_version: Mapped[str] = mapped_column(String(32))
    coverage: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    roll_degrees: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    nose_offset: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)


class ReadingChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (UniqueConstraint("reading_id", "seq", name="uk_chat_message_seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reading_id: Mapped[int] = mapped_column(ForeignKey("reading.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
