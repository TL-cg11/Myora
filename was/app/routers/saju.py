from datetime import date, datetime, time
from importlib.metadata import version
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import optional_user
from app.db import get_session
from app.models import AppUser, Reading, SajuChart, SajuReading
from app.services.saju_dictionary import MissingSajuTerm, lookup_saju_meanings
from app.services.saju_narrative import compose_saju_narrative

router = APIRouter(prefix="/api/saju", tags=["saju"])


class SajuProfileRequest(BaseModel):
    name: str | None = None
    birth_date: date
    birth_time: time | None = None
    gender: Literal["M", "F", "male", "female", "unknown"] | None = None
    guest_key: UUID


def _gender(value: str | None) -> str:
    return {"M": "male", "F": "female"}.get(value or "", value or "unknown")


@router.post("/readings")
def create_saju_reading(
    payload: SajuProfileRequest,
    session: Session = Depends(get_session),
    user: AppUser | None = Depends(optional_user),
) -> dict:
    try:
        from korean_saju import Saju, SajuAnalysis, load_bundled_data
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="korean-saju is not installed.") from exc

    birth = datetime.combine(payload.birth_date, payload.birth_time or time(12, 0))
    saju = Saju.from_birth(
        kst_moment=birth,
        solar_terms=load_bundled_data()[1],
        longitude=126.9784,
        yaja_si_separated=True,
    )
    analysis = SajuAnalysis(saju)
    gender = _gender(payload.gender)
    engine_version = version("korean-saju")
    time_unknown = payload.birth_time is None

    try:
        interpretation = lookup_saju_meanings(session, saju, analysis)
        interpretation['narrative'] = compose_saju_narrative(session, interpretation, time_unknown)
        chart = session.scalar(
            select(SajuChart).where(
                SajuChart.birth_date == payload.birth_date,
                SajuChart.birth_time == payload.birth_time,
                SajuChart.time_unknown == time_unknown,
                SajuChart.gender == gender,
                SajuChart.engine_version == engine_version,
            )
        )
        if chart is None:
            chart = SajuChart(
                birth_date=payload.birth_date,
                birth_time=payload.birth_time,
                time_unknown=time_unknown,
                gender=gender,
                engine_version=engine_version,
                pillar_year=saju.year_pillar.hanja,
                pillar_month=saju.month_pillar.hanja,
                pillar_day=saju.day_pillar.hanja,
                pillar_hour=saju.hour_pillar.hanja if saju.hour_pillar else None,
                jeonggyeok=str(analysis.jeonggyeok)[:40],
                yongsin=str(analysis.yongsin)[:40],
                sinsal=[str(item) for item in analysis.sinsal],
            )
            session.add(chart)
            session.flush()

        reading = Reading(
            service="saju",
            user_id=user.id if user else None,
            guest_key=None if user else str(payload.guest_key),
            summary_title=interpretation['narrative']['title'],
            summary_text=str(saju),
            interpretation_source="rule",
            status="interpreted",
        )
        session.add(reading)
        session.flush()
        session.add(SajuReading(reading_id=reading.id, chart_id=chart.id))
        session.commit()
    except MissingSajuTerm as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail="사주 DB에 연결할 수 없거나 테이블이 준비되지 않았습니다. 기존 사주 스키마와 사전·상담 SQL(12~15번)을 확인해 주세요.",
        ) from exc

    return {
        "status": "ok",
        "reading_id": reading.id,
        "chart_id": chart.id,
        "profile": payload.model_dump(mode="json"),
        "reading": {
            "pillars": str(saju),
            "jeonggyeok": str(analysis.jeonggyeok),
            "yongsin": str(analysis.yongsin),
            "sinsal": [str(item) for item in analysis.sinsal],
            "interpretation": interpretation,
        },
    }


@router.get("/readings")
def list_saju_readings(
    guest_key: UUID,
    limit: int = Query(default=12, ge=1, le=50),
    session: Session = Depends(get_session),
    user: AppUser | None = Depends(optional_user),
) -> list[dict]:
    rows = session.scalars(
        select(Reading)
        .where(
            Reading.service == "saju",
            Reading.user_id == user.id if user else Reading.guest_key == str(guest_key),
        )
        .order_by(Reading.created_at.desc(), Reading.id.desc())
        .limit(limit)
    )
    return [
        {
            "id": row.id,
            "summary_title": row.summary_title,
            "summary_text": row.summary_text,
            "created_at": row.created_at,
        }
        for row in rows
    ]
