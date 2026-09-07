import json
import runpy
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.local_db import initialize
from app.main import app
from app.models import Reading, SajuChart, SajuReading, SajuTerm


class SajuDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        initialize(self.engine)
        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session
        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app)
        self.payload = {'birth_date': '1995-05-15', 'birth_time': '12:00', 'guest_key': str(uuid4())}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def create(self, **kwargs):
        response = self.client.post('/api/saju/readings', json={**self.payload, **kwargs})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_complete_dictionary_covers_engine(self):
        from korean_saju import CheonGan, JiJi, GanJi, Gyeokguk, OHaeng, Sinsal, YongsinMethod
        with Session(self.engine) as session:
            keys = set(session.execute(select(SajuTerm.category, SajuTerm.hanja)).all())
            self.assertEqual(len(keys), 142)
            for category, enum in [('stem', CheonGan), ('branch', JiJi), ('gyeokguk', Gyeokguk), ('element', OHaeng), ('sinsal', Sinsal), ('yongsin_method', YongsinMethod)]:
                self.assertEqual({hanja for cat, hanja in keys if cat == category}, {item.hanja for item in enum})
            self.assertEqual({hanja for cat, hanja in keys if cat == 'ganji'}, {GanJi.by_index(n).hanja for n in range(60)})
            for row in session.scalars(select(SajuTerm)):
                self.assertRegex(row.name_ko, '[가-힣]')
                self.assertRegex(row.meaning_ko, '[가-힣]')

    def test_db_change_is_reflected_next_request_and_seed_preserves_it(self):
        first = self.create()
        entry = first['reading']['interpretation']['pillars'][0]['stem']
        with Session(self.engine) as session:
            session.execute(update(SajuTerm).where(SajuTerm.category == 'stem', SajuTerm.hanja == entry['hanja'])
                            .values(name_ko='수정한 이름', meaning_ko='DB에서 직접 수정한 설명'))
            session.commit()
        initialize(self.engine)
        second = self.create()
        updated = second['reading']['interpretation']['pillars'][0]['stem']
        self.assertEqual(updated['meaning_ko'], 'DB에서 직접 수정한 설명')
        self.assertEqual(updated['name_ko'], '수정한 이름')
        self.assertEqual(first['chart_id'], second['chart_id'])
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(SajuTerm)), 142)

    def test_missing_entry_does_not_fallback_or_partially_save(self):
        with Session(self.engine) as session:
            session.execute(delete(SajuTerm).where(SajuTerm.category == 'element'))
            session.commit()
        response = self.client.post('/api/saju/readings', json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertIn('사전 데이터가 누락', response.json()['detail'])
        with Session(self.engine) as session:
            for model in (Reading, SajuChart, SajuReading):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 0)

    def test_existing_response_and_raw_storage_are_preserved(self):
        body = self.create()
        self.assertTrue({'status','reading_id','chart_id','profile','reading'} <= body.keys())
        self.assertTrue({'pillars','jeonggyeok','yongsin','sinsal','interpretation'} <= body['reading'].keys())
        self.assertEqual(body['reading']['interpretation']['source'], 'database')
        with Session(self.engine) as session:
            self.assertEqual(session.get(Reading, body['reading_id']).summary_text, body['reading']['pillars'])
            self.assertIsNotNone(session.get(SajuReading, body['reading_id']))
        self.assertNotIn('interpretation_ko', SajuReading.__table__.c)
        self.assertEqual(self.client.get('/api/saju/readings', params={'guest_key':self.payload['guest_key']}).status_code, 405)

    def test_multiple_birth_dates_use_registered_terms(self):
        for birth_date, birth_time in [('1800-01-01',None),('2100-12-31','23:30'),('2000-02-29','00:00'),('1988-08-08','08:00')]:
            self.create(birth_date=birth_date, birth_time=birth_time)

    def test_sql_seed_matches_json(self):
        root = Path(__file__).resolve().parents[2]
        rows = json.loads((root/'app/data/saju_terms.json').read_text(encoding='utf-8'))
        render = runpy.run_path(str(root/'scripts/export-saju-dictionary.py'))['render_sql']
        sql = root.parent/'luck-mariadb/sql/init/13_saju_dictionary_seed.sql'
        if not sql.exists():
            self.skipTest('Separate MariaDB repository is not available')
        self.assertEqual(sql.read_text(encoding='utf-8'), render(rows))
