import json
import runpy
import unittest
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.local_db import initialize
from app.models import Reading, SajuNarrativeRule
from app.services.saju_narrative import Advice, DayProfile
from app.tests import test_saju_dictionary


class SajuNarrativeTests(unittest.TestCase):
    setUp = test_saju_dictionary.SajuDictionaryTests.setUp
    tearDown = test_saju_dictionary.SajuDictionaryTests.tearDown
    create = test_saju_dictionary.SajuDictionaryTests.create

    def test_all_sixty_profiles_and_modifiers_are_valid(self):
        from korean_saju import GanJi
        with Session(self.engine) as session:
            rows = session.scalars(select(SajuNarrativeRule)).all()
        self.assertEqual(len(rows), 105)
        profiles = {row.hanja: DayProfile.model_validate(row.data) for row in rows if row.category == 'day'}
        self.assertEqual(set(profiles), {GanJi.by_index(n).hanja for n in range(60)})
        for n in range(60):
            pair = GanJi.by_index(n)
            self.assertEqual(profiles[pair.hanja].code, pair.hangul)
        for row in rows:
            if row.category != 'day':
                Advice.model_validate(row.data)

    def test_byeong_o_example_and_different_day(self):
        first = self.create()['reading']['interpretation']['narrative']
        self.assertEqual(first['profile']['code'], '병오')
        self.assertEqual(first['profile']['keywords'], ['활동적','추진력','표현력','승부욕'])
        second = self.create(birth_date='1995-05-16')['reading']['interpretation']['narrative']
        self.assertNotEqual(first['overview'], second['overview'])
        self.assertNotEqual(first['sections'], second['sections'])
        self.assertEqual(first, self.create()['reading']['interpretation']['narrative'])

    def test_same_day_different_month_changes_combined_advice(self):
        first = self.create()['reading']['interpretation']['narrative']
        second = self.create(birth_date='1995-07-14')['reading']['interpretation']['narrative']
        self.assertEqual(first['profile'], second['profile'])
        self.assertNotEqual(first['sections'], second['sections'])

    def test_db_profile_edit_is_immediate_and_seed_preserves_it(self):
        with Session(self.engine) as session:
            rule = session.scalar(select(SajuNarrativeRule).where(SajuNarrativeRule.category == 'day', SajuNarrativeRule.hanja == '丙午'))
            data = {**rule.data, 'intro': 'DB에서 바꾼 나만의 상담 문장입니다.'}
            rule.data = data
            session.commit()
        initialize(self.engine)
        story = self.create()['reading']['interpretation']['narrative']
        self.assertEqual(story['overview'][0], data['intro'])

    def test_missing_or_invalid_profile_rolls_back_reading(self):
        with Session(self.engine) as session:
            session.execute(update(SajuNarrativeRule).where(SajuNarrativeRule.category == 'day').values(data={}))
            session.commit()
        response = self.client.post('/api/saju/readings', json=self.payload)
        self.assertEqual(response.status_code, 503)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Reading)), 0)
            session.execute(delete(SajuNarrativeRule))
            session.commit()
        self.assertEqual(self.client.post('/api/saju/readings', json=self.payload).status_code, 503)

    def test_unknown_time_is_explained(self):
        story = self.create(birth_time=None)['reading']['interpretation']['narrative']
        self.assertIn('정오', story['notice'])

    def test_narrative_sql_matches_seed(self):
        root = Path(__file__).resolve().parents[2]
        rows = json.loads((root/'app/data/saju_narratives.json').read_text(encoding='utf8'))
        render = runpy.run_path(str(root/'scripts/export-saju-dictionary.py'))['render_narrative_sql']
        sql = root.parent/'luck-mariadb/sql/init/15_saju_narrative_seed.sql'
        if not sql.exists():
            self.skipTest('Separate MariaDB repository is not available')
        self.assertEqual(sql.read_text(encoding='utf8'), render(rows))
