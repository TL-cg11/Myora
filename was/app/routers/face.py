"""관상 측정값 저장 및 비회원 기록 조회 API."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session
from app.auth import optional_user
from app.models import AppUser, FaceReading, FaceShape, Reading
from app.schemas import FaceReadingCreate, FaceReadingOut
from app.services import face as service


router = APIRouter(prefix="/api/face", tags=["face"])
logger = logging.getLogger(__name__)


def _to_out(
    reading: Reading,
    detail: FaceReading | None,
    shape: FaceShape,
    keywords: list[str] | None = None,
) -> FaceReadingOut:
    return FaceReadingOut(
        id=reading.id,
        shape_code=shape.code,
        summary_title=reading.summary_title or shape.title,
        summary_text=reading.summary_text or "",
        mood=detail.mood if detail is not None else None,
        created_at=reading.created_at,
        keywords=keywords or [shape.keyword],
    )


@router.post(
    "/readings", response_model=FaceReadingOut, status_code=status.HTTP_201_CREATED
)
def create_face_reading(
    payload: FaceReadingCreate,
    session: Session = Depends(get_session),
    user: AppUser | None = Depends(optional_user),
) -> FaceReadingOut:
    try:
        reading, shape, keywords = service.save_face_reading(
            session, payload, user_id=user.id if user else None
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("관상 결과 저장 실패")
        raise HTTPException(
            status_code=503,
            detail="관상 결과를 저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.",
        ) from exc

    return _to_out(reading, None, shape, keywords).model_copy(update={"mood": payload.mood})


@router.get("/readings", response_model=list[FaceReadingOut])
def get_face_readings(
    guest_key: UUID,
    limit: int = Query(default=12, ge=1, le=50),
    session: Session = Depends(get_session),
    user: AppUser | None = Depends(optional_user),
) -> list[FaceReadingOut]:
    return [
        _to_out(reading, detail, shape)
        for reading, detail, shape in service.list_face_readings(
            session, guest_key=str(guest_key), user_id=user.id if user else None, limit=limit
        )
    ]
