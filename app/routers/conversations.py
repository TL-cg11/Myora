"""Authenticated endpoints for a member's saved conversation history."""

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.auth import current_user
from app.conversation_schemas import ConversationDetailOut, ConversationPageOut
from app.db import get_session
from app.models import AppUser
from app.services.conversation_history import get_user_conversation, list_user_conversations


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=ConversationPageOut)
def list_my_conversations(
    service: Literal["all", "saju", "tarot", "face"] = "all",
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    session: Session = Depends(get_session),
    user: AppUser = Depends(current_user),
) -> ConversationPageOut:
    return list_user_conversations(
        session, user_id=user.id, service=service, limit=limit, cursor=cursor
    )


@router.get("/{service}/{reading_id}", response_model=ConversationDetailOut)
def get_my_conversation(
    service: Literal["saju", "tarot", "face"],
    reading_id: int = Path(gt=0),
    session: Session = Depends(get_session),
    user: AppUser = Depends(current_user),
) -> ConversationDetailOut:
    return get_user_conversation(
        session, user_id=user.id, service=service, reading_id=reading_id
    )
