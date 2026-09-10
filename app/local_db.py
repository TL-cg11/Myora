"""로컬 SQLite 전용 초기화. 운영 모델/테이블은 수정하지 않는다."""
import json
from pathlib import Path

from sqlalchemy import Integer, MetaData, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, AuthSession, Reading, ReadingChatMessage, SajuChart, SajuReading, SajuTerm, SajuNarrativeRule


def initialize(local_engine=engine):
    if local_engine.dialect.name != "sqlite":
        raise RuntimeError("SQLite 전용 초기화입니다. 운영 DB는 SQL 파일로 적용하세요.")
    metadata = MetaData()
    for model in (AppUser, AuthSession, Reading, ReadingChatMessage, SajuChart, SajuReading, SajuTerm, SajuNarrativeRule):
        table = model.__table__.to_metadata(metadata)
        if model in (AppUser, AuthSession, Reading, ReadingChatMessage, SajuChart):
            # SQLite는 INTEGER PRIMARY KEY만 자동 증가한다. 원본 ORM은 유지한다.
            table.c.id.type = Integer()
    metadata.create_all(local_engine)
    rows = json.loads((Path(__file__).parent / "data/saju_terms.json").read_text(encoding="utf-8"))
    with Session(local_engine) as session:
        existing = set(session.execute(select(SajuTerm.category, SajuTerm.hanja)).all())
        session.add_all(SajuTerm(**row) for row in rows if (row['category'], row['hanja']) not in existing)
        narrative_rows = json.loads((Path(__file__).parent / "data/saju_narratives.json").read_text(encoding="utf-8"))
        narrative_existing = set(session.execute(select(SajuNarrativeRule.category, SajuNarrativeRule.hanja)).all())
        session.add_all(SajuNarrativeRule(**row) for row in narrative_rows
                        if (row['category'], row['hanja']) not in narrative_existing)
        session.commit()


if __name__ == "__main__":
    initialize()
