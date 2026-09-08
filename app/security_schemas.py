"""위험 이벤트 조회 API 응답 계약."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.security_models import (
    SecurityActionType,
    SecurityActorType,
    SecurityEventStatus,
    SecurityRiskLevel,
)


class SecurityEventSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    source_event_id: str
    request_id: str | None
    occurred_at: datetime
    detected_at: datetime
    environment: str
    source_service: str
    source_type: str
    event_name: str | None
    risk_level: SecurityRiskLevel
    risk_score: int
    status: SecurityEventStatus
    assigned_to: str | None
    masked_excerpt: str | None
    created_at: datetime
    updated_at: datetime


class SecurityEventDetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detection_id: str
    rule_id: str
    rule_version: str
    category: str
    entity_type: str
    risk_level: SecurityRiskLevel
    confidence: float
    match_count: int
    evidence_fingerprint: str | None
    locations_json: Any | None
    created_at: datetime


class SecurityEventActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action_type: SecurityActionType
    actor_type: SecurityActorType
    actor_id: str
    previous_status: str | None
    new_status: str | None
    previous_assignee: str | None
    new_assignee: str | None
    reason: str | None
    acted_at: datetime


class SecurityEventDetailOut(SecurityEventSummaryOut):
    schema_version: str
    detector_version: str
    masking_policy_version: str
    body_hash: str | None
    resolution_reason: str | None
    resolved_at: datetime | None
    safe_metadata: Any | None
    detections: list[SecurityEventDetectionOut] = Field(default_factory=list)
    actions: list[SecurityEventActionOut] = Field(default_factory=list)


class SecurityEventPageOut(BaseModel):
    items: list[SecurityEventSummaryOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class SecurityEventStatusUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SecurityEventStatus
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)


class SecurityEventAssigneeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to: str = Field(min_length=1, max_length=128)


class SecurityEventFalsePositiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_reason: str = Field(min_length=1, max_length=2_000)


class SecurityEventReopenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, min_length=1, max_length=2_000)


class SecurityAuditLogOut(BaseModel):
    event_id: str
    action_type: SecurityActionType
    actor_type: SecurityActorType
    actor_id: str
    previous_status: str | None
    new_status: str | None
    previous_assignee: str | None
    new_assignee: str | None
    reason: str | None
    acted_at: datetime


class SecurityAuditLogPageOut(BaseModel):
    items: list[SecurityAuditLogOut]
    page: int
    page_size: int
    total: int
    total_pages: int
