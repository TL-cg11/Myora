"""append-only 보안 이벤트 감사 로그 조회 API."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.security_auth import Permission, SecurityPrincipal, require_permissions
from app.security_db import get_security_session
from app.security_models import SecurityActionType, SecurityEvent, SecurityEventAction
from app.security_schemas import SecurityAuditLogOut, SecurityAuditLogPageOut


router = APIRouter(prefix="/api/security/audit-logs", tags=["security-audit"])
AuditReader = Annotated[
    SecurityPrincipal, Depends(require_permissions(Permission.AUDIT_READ))
]


def _database_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("", response_model=SecurityAuditLogPageOut)
def list_security_audit_logs(
    _principal: AuditReader,
    session: Annotated[Session, Depends(get_security_session)],
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    event_id: str | None = Query(default=None, min_length=1, max_length=64),
    actor_id: str | None = Query(default=None, min_length=1, max_length=128),
    action_type: SecurityActionType | None = Query(default=None),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> SecurityAuditLogPageOut:
    start = _database_datetime(start_time)
    end = _database_datetime(end_time)
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_time must not be later than end_time",
        )

    filters = []
    if start is not None:
        filters.append(SecurityEventAction.acted_at >= start)
    if end is not None:
        filters.append(SecurityEventAction.acted_at <= end)
    if event_id is not None:
        filters.append(SecurityEvent.event_id == event_id)
    if actor_id is not None:
        filters.append(SecurityEventAction.actor_id == actor_id)
    if action_type is not None:
        filters.append(SecurityEventAction.action_type == action_type)

    joined = SecurityEventAction.__table__.join(
        SecurityEvent.__table__,
        SecurityEventAction.security_event_id == SecurityEvent.id,
    )
    total = session.scalar(
        select(func.count(SecurityEventAction.id)).select_from(joined).where(*filters)
    ) or 0
    ordering = asc if sort_order == "asc" else desc
    statement = (
        select(SecurityEventAction, SecurityEvent.event_id)
        .join(SecurityEvent, SecurityEventAction.security_event_id == SecurityEvent.id)
        .where(*filters)
        .order_by(
            ordering(SecurityEventAction.acted_at),
            ordering(SecurityEventAction.id),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        SecurityAuditLogOut(
            event_id=public_event_id,
            action_type=action.action_type,
            actor_type=action.actor_type,
            actor_id=action.actor_id,
            previous_status=action.previous_status,
            new_status=action.new_status,
            previous_assignee=action.previous_assignee,
            new_assignee=action.new_assignee,
            reason=action.reason,
            acted_at=action.acted_at,
        )
        for action, public_event_id in session.execute(statement)
    ]
    return SecurityAuditLogPageOut(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


def _audit_log_mutation_error() -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Security audit logs are append-only",
    )


@router.api_route("", methods=["POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def reject_audit_log_collection_mutation(_principal: AuditReader) -> None:
    _audit_log_mutation_error()


@router.api_route(
    "/{audit_path:path}",
    methods=["POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def reject_audit_log_item_mutation(
    audit_path: str,
    _principal: AuditReader,
) -> None:
    del audit_path
    _audit_log_mutation_error()
