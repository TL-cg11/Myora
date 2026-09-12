"""위험 이벤트 상태 변경과 append-only 감사 action 처리."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.security_auth import SecurityPrincipal
from app.security_models import (
    SecurityActionType,
    SecurityActorType,
    SecurityEvent,
    SecurityEventAction,
    SecurityEventStatus,
    SecurityUser,
    SecurityUserStatus,
)


ALLOWED_STATUS_TRANSITIONS = frozenset(
    {
        (SecurityEventStatus.OPEN, SecurityEventStatus.INVESTIGATING),
        (SecurityEventStatus.OPEN, SecurityEventStatus.FALSE_POSITIVE),
        (SecurityEventStatus.INVESTIGATING, SecurityEventStatus.RESOLVED),
        (SecurityEventStatus.INVESTIGATING, SecurityEventStatus.FALSE_POSITIVE),
        (SecurityEventStatus.RESOLVED, SecurityEventStatus.OPEN),
        (SecurityEventStatus.FALSE_POSITIVE, SecurityEventStatus.OPEN),
    }
)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lock_event(session: Session, event_id: str) -> SecurityEvent:
    event = session.scalars(
        select(SecurityEvent)
        .where(SecurityEvent.event_id == event_id)
        .with_for_update()
    ).one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security event not found",
        )
    return event


def require_transition(
    previous: SecurityEventStatus, target: SecurityEventStatus
) -> None:
    if (previous, target) not in ALLOWED_STATUS_TRANSITIONS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid security event transition: {previous.value} -> {target.value}",
        )


def append_user_action(
    session: Session,
    event: SecurityEvent,
    principal: SecurityPrincipal,
    action_type: SecurityActionType,
    *,
    previous_status: SecurityEventStatus | None = None,
    new_status: SecurityEventStatus | None = None,
    previous_assignee: str | None = None,
    new_assignee: str | None = None,
    reason: str | None = None,
) -> None:
    """INSERT만 제공한다. action 수정·삭제 함수와 API는 만들지 않는다."""
    session.add(
        SecurityEventAction(
            security_event_id=event.id,
            action_type=action_type,
            actor_type=SecurityActorType.USER,
            actor_id=principal.actor_id,
            previous_status=previous_status.value if previous_status else None,
            new_status=new_status.value if new_status else None,
            previous_assignee=previous_assignee,
            new_assignee=new_assignee,
            reason=reason,
            acted_at=utc_now_naive(),
        )
    )


def change_status(
    session: Session,
    event_id: str,
    target: SecurityEventStatus,
    principal: SecurityPrincipal,
    reason: str | None = None,
) -> None:
    event = lock_event(session, event_id)
    previous = event.status
    require_transition(previous, target)
    if target in {SecurityEventStatus.FALSE_POSITIVE, SecurityEventStatus.OPEN}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use the false-positive or reopen endpoint for this transition",
        )

    event.status = target
    if target is SecurityEventStatus.RESOLVED:
        event.resolved_at = utc_now_naive()
        action_type = SecurityActionType.RESOLVED
    else:
        action_type = SecurityActionType.STATUS_CHANGED
    append_user_action(
        session,
        event,
        principal,
        action_type,
        previous_status=previous,
        new_status=target,
        reason=reason,
    )
    session.commit()


def assign_event(
    session: Session,
    event_id: str,
    assignee_actor_id: str,
    principal: SecurityPrincipal,
) -> None:
    event = lock_event(session, event_id)
    assignee = session.scalars(
        select(SecurityUser).where(
            SecurityUser.actor_id == assignee_actor_id,
            SecurityUser.status == SecurityUserStatus.ACTIVE,
        )
    ).one_or_none()
    if assignee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active security assignee not found",
        )
    previous_assignee = event.assigned_to
    if previous_assignee == assignee_actor_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Security event is already assigned to this user",
        )

    event.assigned_to = assignee_actor_id
    append_user_action(
        session,
        event,
        principal,
        SecurityActionType.ASSIGNED,
        previous_assignee=previous_assignee,
        new_assignee=assignee_actor_id,
    )
    session.commit()


def mark_false_positive(
    session: Session,
    event_id: str,
    resolution_reason: str,
    principal: SecurityPrincipal,
) -> None:
    event = lock_event(session, event_id)
    previous = event.status
    target = SecurityEventStatus.FALSE_POSITIVE
    require_transition(previous, target)

    event.status = target
    event.resolution_reason = resolution_reason
    event.resolved_at = utc_now_naive()
    append_user_action(
        session,
        event,
        principal,
        SecurityActionType.MARKED_FALSE_POSITIVE,
        previous_status=previous,
        new_status=target,
        reason=resolution_reason,
    )
    session.commit()


def reopen_event(
    session: Session,
    event_id: str,
    principal: SecurityPrincipal,
    reason: str | None = None,
) -> None:
    event = lock_event(session, event_id)
    previous = event.status
    target = SecurityEventStatus.OPEN
    require_transition(previous, target)

    event.status = target
    event.resolution_reason = None
    event.resolved_at = None
    append_user_action(
        session,
        event,
        principal,
        SecurityActionType.REOPENED,
        previous_status=previous,
        new_status=target,
        reason=reason,
    )
    session.commit()
