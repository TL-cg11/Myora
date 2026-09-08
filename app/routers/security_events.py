"""인증된 관제 사용자를 위한 위험 이벤트 조회 API."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.security_auth import Permission, SecurityPrincipal, require_permissions
from app.security_db import get_security_session
from app.security_event_actions import (
    assign_event,
    change_status,
    mark_false_positive,
    reopen_event,
)
from app.security_models import (
    SecurityEvent,
    SecurityEventStatus,
    SecurityRiskLevel,
)
from app.security_schemas import (
    SecurityEventAssigneeIn,
    SecurityEventDetailOut,
    SecurityEventFalsePositiveIn,
    SecurityEventPageOut,
    SecurityEventReopenIn,
    SecurityEventStatusUpdateIn,
)


router = APIRouter(prefix="/api/security/events", tags=["security-events"])
EventReader = Annotated[
    SecurityPrincipal, Depends(require_permissions(Permission.EVENT_READ))
]
StatusEditor = Annotated[
    SecurityPrincipal, Depends(require_permissions(Permission.EVENT_STATUS_UPDATE))
]
AssigneeEditor = Annotated[
    SecurityPrincipal, Depends(require_permissions(Permission.EVENT_ASSIGN))
]
FalsePositiveEditor = Annotated[
    SecurityPrincipal, Depends(require_permissions(Permission.EVENT_FALSE_POSITIVE))
]
ReopenEditor = Annotated[
    SecurityPrincipal, Depends(require_permissions(Permission.EVENT_REOPEN))
]


class EventSortField(str, Enum):
    OCCURRED_AT = "occurred_at"
    DETECTED_AT = "detected_at"
    RISK_SCORE = "risk_score"
    CREATED_AT = "created_at"


def _database_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _event_detail(session: Session, event_id: str) -> SecurityEvent:
    statement = (
        select(SecurityEvent)
        .where(SecurityEvent.event_id == event_id)
        .options(
            selectinload(SecurityEvent.detections),
            selectinload(SecurityEvent.actions),
        )
        .execution_options(populate_existing=True)
    )
    event = session.scalars(statement).one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security event not found",
        )
    return event


@router.get("", response_model=SecurityEventPageOut)
def list_security_events(
    _principal: EventReader,
    session: Annotated[Session, Depends(get_security_session)],
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    risk_level: SecurityRiskLevel | None = Query(default=None),
    event_status: SecurityEventStatus | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None, min_length=1, max_length=64),
    sort_by: EventSortField = Query(default=EventSortField.DETECTED_AT),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> SecurityEventPageOut:
    start = _database_datetime(start_time)
    end = _database_datetime(end_time)
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_time must not be later than end_time",
        )

    filters = []
    if start is not None:
        filters.append(SecurityEvent.detected_at >= start)
    if end is not None:
        filters.append(SecurityEvent.detected_at <= end)
    if risk_level is not None:
        filters.append(SecurityEvent.risk_level == risk_level)
    if event_status is not None:
        filters.append(SecurityEvent.status == event_status)
    if source is not None:
        filters.append(
            or_(
                SecurityEvent.source_service == source,
                SecurityEvent.source_type == source,
            )
        )

    total = session.scalar(select(func.count(SecurityEvent.id)).where(*filters)) or 0
    sort_column = {
        EventSortField.OCCURRED_AT: SecurityEvent.occurred_at,
        EventSortField.DETECTED_AT: SecurityEvent.detected_at,
        EventSortField.RISK_SCORE: SecurityEvent.risk_score,
        EventSortField.CREATED_AT: SecurityEvent.created_at,
    }[sort_by]
    ordering = asc if sort_order == "asc" else desc
    statement = (
        select(SecurityEvent)
        .where(*filters)
        .order_by(ordering(sort_column), ordering(SecurityEvent.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(session.scalars(statement))
    return SecurityEventPageOut(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{event_id}", response_model=SecurityEventDetailOut)
def get_security_event(
    _principal: EventReader,
    session: Annotated[Session, Depends(get_security_session)],
    event_id: str = Path(min_length=1, max_length=64),
) -> SecurityEvent:
    return _event_detail(session, event_id)


@router.patch("/{event_id}/status", response_model=SecurityEventDetailOut)
def update_security_event_status(
    payload: SecurityEventStatusUpdateIn,
    principal: StatusEditor,
    session: Annotated[Session, Depends(get_security_session)],
    event_id: str = Path(min_length=1, max_length=64),
) -> SecurityEvent:
    change_status(session, event_id, payload.status, principal, payload.reason)
    return _event_detail(session, event_id)


@router.patch("/{event_id}/assignee", response_model=SecurityEventDetailOut)
def update_security_event_assignee(
    payload: SecurityEventAssigneeIn,
    principal: AssigneeEditor,
    session: Annotated[Session, Depends(get_security_session)],
    event_id: str = Path(min_length=1, max_length=64),
) -> SecurityEvent:
    assign_event(session, event_id, payload.assigned_to, principal)
    return _event_detail(session, event_id)


@router.post("/{event_id}/false-positive", response_model=SecurityEventDetailOut)
def false_positive_security_event(
    payload: SecurityEventFalsePositiveIn,
    principal: FalsePositiveEditor,
    session: Annotated[Session, Depends(get_security_session)],
    event_id: str = Path(min_length=1, max_length=64),
) -> SecurityEvent:
    mark_false_positive(
        session, event_id, payload.resolution_reason, principal
    )
    return _event_detail(session, event_id)


@router.post("/{event_id}/reopen", response_model=SecurityEventDetailOut)
def reopen_security_event(
    payload: SecurityEventReopenIn,
    principal: ReopenEditor,
    session: Annotated[Session, Depends(get_security_session)],
    event_id: str = Path(min_length=1, max_length=64),
) -> SecurityEvent:
    reopen_event(session, event_id, principal, payload.reason)
    return _event_detail(session, event_id)
