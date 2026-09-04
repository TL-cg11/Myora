from datetime import date, datetime, time
from importlib.metadata import version
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Reading, SajuChart, SajuReading

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
def create_saju_reading(payload: SajuProfileRequest, session: Session = Depends(get_session)) -> dict:
    try:
        from korean_saju import Saju, SajuAnalysis, load_bundled_data
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Install korean-saju first") from exc

    birth = datetime.combine(payload.birth_date, payload.birth_time or time(12, 0))
    saju = Saju.from_birth(kst_moment=birth, solar_terms=load_bundled_data()[1], longitude=126.9784, yaja_si_separated=True)
    analysis = SajuAnalysis(saju)
    chart = SajuChart(
        birth_date=payload.birth_date, birth_time=payload.birth_time,
        time_unknown=payload.birth_time is None, gender=_gender(payload.gender),
        engine_version=version("korean-saju"), pillar_year=str(saju.year_pillar),
        pillar_month=str(saju.month_pillar), pillar_day=str(saju.day_pillar),
        pillar_hour=str(saju.hour_pillar) if saju.hour_pillar else None,
        jeonggyeok=str(analysis.jeonggyeok), yongsin=str(analysis.yongsin),
        sinsal=[str(item) for item in analysis.sinsal],
    )
    reading = Reading(service="saju", guest_key=str(payload.guest_key), summary_title="사주 계산 결과", summary_text=str(saju), interpretation_source="rule", status="interpreted")
    session.add_all([chart, reading])
    session.flush()
    session.add(SajuReading(reading_id=reading.id, chart_id=chart.id))
    session.commit()
    return {"status": "ok", "reading_id": reading.id, "chart_id": chart.id, "profile": payload.model_dump(mode="json"), "reading": {"pillars": str(saju), "jeonggyeok": str(analysis.jeonggyeok), "yongsin": str(analysis.yongsin), "sinsal": [str(item) for item in analysis.sinsal]}}
