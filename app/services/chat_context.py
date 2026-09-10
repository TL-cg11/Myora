"""Read authorized results and serialize only model-visible fields."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Reading, SajuReading, SajuChart, FaceReading


def load_context(session, service, reading_id, guest_key, user):
    condition = Reading.user_id == user.id if user else (Reading.user_id.is_(None) & (Reading.guest_key == str(guest_key)))
    reading = session.scalar(select(Reading).where(Reading.id == reading_id, Reading.service == service, condition).with_for_update())
    if reading is None:
        raise HTTPException(404, '리딩을 찾을 수 없어요.')
    if service == 'saju':
        row = session.scalar(select(SajuChart).join(SajuReading, SajuReading.chart_id == SajuChart.id).where(SajuReading.reading_id == reading_id))
        fields = ('pillar_year','pillar_month','pillar_day','pillar_hour','jeonggyeok','yongsin','sinsal','time_unknown')
    else:
        row = session.get(FaceReading, reading_id)
        fields = ('aspect_ratio','jaw_ratio','forehead_ratio','eye_ratio','mouth_ratio','symmetry_score')
    if row is None:
        raise HTTPException(404, '상담에 필요한 결과를 찾을 수 없어요.')
    context = {
        "summary_title": reading.summary_title,
        "summary_text": reading.summary_text,
        "result": {field: getattr(row, field) for field in fields},
    }
    return json.dumps(context, ensure_ascii=False, default=str)
