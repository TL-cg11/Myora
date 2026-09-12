"""security_monitoring 사용자·역할 ORM 모델."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class SecurityBase(DeclarativeBase):
    pass


class SecurityUserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SecurityRoleCode(str, enum.Enum):
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"
    ADMIN = "ADMIN"


class SecurityRiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEventStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class SecurityActionType(str, enum.Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    STATUS_CHANGED = "STATUS_CHANGED"
    COMMENTED = "COMMENTED"
    RESOLVED = "RESOLVED"
    MARKED_FALSE_POSITIVE = "MARKED_FALSE_POSITIVE"
    REOPENED = "REOPENED"


class SecurityActorType(str, enum.Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"


def _enum(python_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(
        python_enum,
        name=name,
        values_callable=lambda values: [value.value for value in values],
    )


class SecurityUserRole(SecurityBase):
    __tablename__ = "security_user_role"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("security_user.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("security_role.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SecurityUser(SecurityBase):
    __tablename__ = "security_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[SecurityUserStatus] = mapped_column(
        _enum(SecurityUserStatus, "security_user_status"),
        default=SecurityUserStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    roles: Mapped[list["SecurityRole"]] = relationship(
        secondary="security_user_role", lazy="selectin", viewonly=True
    )


class SecurityRole(SecurityBase):
    __tablename__ = "security_role"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_code: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SecurityEvent(SecurityBase):
    __tablename__ = "security_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    source_event_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    environment: Mapped[str] = mapped_column(String(32))
    source_service: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(64))
    event_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[SecurityRiskLevel] = mapped_column(
        _enum(SecurityRiskLevel, "security_risk_level")
    )
    risk_score: Mapped[int] = mapped_column(SmallInteger)
    detector_version: Mapped[str] = mapped_column(String(32))
    masking_policy_version: Mapped[str] = mapped_column(String(32))
    masked_excerpt: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    body_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[SecurityEventStatus] = mapped_column(
        _enum(SecurityEventStatus, "security_event_status"),
        default=SecurityEventStatus.OPEN,
    )
    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    safe_metadata: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    detections: Mapped[list["SecurityEventDetection"]] = relationship(
        back_populates="event", lazy="raise", order_by="SecurityEventDetection.id"
    )
    actions: Mapped[list["SecurityEventAction"]] = relationship(
        back_populates="event", lazy="raise", order_by="SecurityEventAction.acted_at"
    )


class SecurityEventDetection(SecurityBase):
    __tablename__ = "security_event_detection"

    id: Mapped[int] = mapped_column(primary_key=True)
    security_event_id: Mapped[int] = mapped_column(
        ForeignKey("security_event.id", ondelete="RESTRICT")
    )
    detection_id: Mapped[str] = mapped_column(String(64), unique=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(64))
    risk_level: Mapped[SecurityRiskLevel] = mapped_column(
        _enum(SecurityRiskLevel, "detection_risk_level")
    )
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    match_count: Mapped[int] = mapped_column(Integer, default=1)
    evidence_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    locations_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    event: Mapped[SecurityEvent] = relationship(back_populates="detections")


class SecurityEventAction(SecurityBase):
    __tablename__ = "security_event_action"

    id: Mapped[int] = mapped_column(primary_key=True)
    security_event_id: Mapped[int] = mapped_column(
        ForeignKey("security_event.id", ondelete="RESTRICT")
    )
    action_type: Mapped[SecurityActionType] = mapped_column(
        _enum(SecurityActionType, "security_action_type")
    )
    actor_type: Mapped[SecurityActorType] = mapped_column(
        _enum(SecurityActorType, "security_actor_type")
    )
    actor_id: Mapped[str] = mapped_column(String(128))
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    previous_assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    new_assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    event: Mapped[SecurityEvent] = relationship(back_populates="actions")
