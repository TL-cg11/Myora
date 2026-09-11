import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import question_limit_for
from app.config import settings
from app.db import get_session
from app.local_db import initialize
from app.main import app
from app.models import AppUser, AppUserRole, FaceReading, Reading
from app.routers.chat import ChatRequest, reading_chat
from app.services.guardrail import SafeAnswer


class QuestionLimitHelperTests(unittest.TestCase):
    """관리자 판별과 한도 계산은 이 헬퍼 하나로 모은다.

    호출부(chat.py, tarot_chat.py, main.py)가 각자 role을 비교하면 판단 기준이
    갈라지기 쉽다.
    """

    def test_guest_and_regular_user_get_the_common_limit(self):
        self.assertEqual(question_limit_for(None), settings.chat_question_limit)
        regular = AppUser(role=AppUserRole.user)
        self.assertEqual(question_limit_for(regular), settings.chat_question_limit)

    def test_admin_gets_the_extended_limit(self):
        admin = AppUser(role=AppUserRole.admin)
        self.assertTrue(admin.is_admin)
        self.assertEqual(question_limit_for(admin), settings.chat_question_limit_admin)

    def test_admin_limit_is_not_smaller_than_the_common_limit(self):
        # 값 자체는 운영에서 바뀔 수 있지만, 관리자 한도가 일반 한도보다 낮아지는
        # 설정은 이 기능의 목적과 모순된다.
        self.assertGreaterEqual(
            settings.chat_question_limit_admin, settings.chat_question_limit
        )


class AdminReadingChatTests(unittest.IsolatedAsyncioTestCase):
    """reading_chat이 실제로 관리자 한도를 적용하는지 본다."""

    def setUp(self):
        self.engine = create_engine('sqlite://')
        from app.models import Base
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        self.admin = AppUser(
            id=1, username='admin', name='관리자', email='admin@example.com',
            password_hash='x', role=AppUserRole.admin,
        )
        self.session.add(self.admin)
        self.session.add(Reading(id=1, service='face', user_id=1, guest_key=None))
        self.session.add(FaceReading(
            reading_id=1, aspect_ratio=1.3, jaw_ratio=.8, forehead_ratio=.8,
            eye_ratio=.2, mouth_ratio=.3, symmetry_score=.9, detector_version='test',
        ))
        self.session.commit()

    def request(self):
        return ChatRequest(reading_id=1, guest_key=uuid4(), message='얼굴형 설명')

    async def test_admin_can_ask_past_the_common_limit(self):
        with patch('app.routers.chat.safe_answer',
                   AsyncMock(return_value=SafeAnswer('안전 답변', '질문', True))) as call:
            # 일반 한도(기본 5회)를 넘겨도 관리자 한도(기본 20회) 안이면 계속된다.
            for index in range(settings.chat_question_limit + 1):
                result = await reading_chat('face', 'persona', self.request(), self.session, self.admin)
                self.assertEqual(result.questions_used, index + 1)
        self.assertEqual(call.await_count, settings.chat_question_limit + 1)

    async def test_admin_still_stops_at_the_admin_limit(self):
        with patch('app.routers.chat.safe_answer',
                   AsyncMock(return_value=SafeAnswer('안전 답변', '질문', True))):
            for _ in range(settings.chat_question_limit_admin):
                await reading_chat('face', 'persona', self.request(), self.session, self.admin)
            with self.assertRaises(HTTPException) as raised:
                await reading_chat('face', 'persona', self.request(), self.session, self.admin)
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn(str(settings.chat_question_limit_admin), raised.exception.detail)


class ApiConfigRoleAwareTests(unittest.TestCase):
    """/api/config가 로그인 계정의 역할에 따라 다른 한도를 내려주는지 본다."""

    def setUp(self):
        self.engine = create_engine(
            'sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
        )
        initialize(self.engine)

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(self.engine.dispose)

    def register(self):
        response = self.client.post('/api/auth/register', json={
            'username': 'admin_test', 'name': '관리자', 'password': 'safe-password-123',
            'email': 'admin_test@example.com', 'guest_key': str(uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_anonymous_request_gets_the_common_limit(self):
        response = self.client.get('/api/config')
        self.assertEqual(response.json()['chat_question_limit'], settings.chat_question_limit)

    def test_admin_account_gets_the_extended_limit(self):
        registered = self.register()
        with Session(self.engine) as session:
            session.execute(
                update(AppUser).where(AppUser.username == 'admin_test')
                .values(role=AppUserRole.admin)
            )
            session.commit()
        headers = {'Authorization': f"Bearer {registered['access_token']}"}
        response = self.client.get('/api/config', headers=headers)
        self.assertEqual(response.json()['chat_question_limit'], settings.chat_question_limit_admin)

    def test_regular_account_keeps_the_common_limit(self):
        registered = self.register()
        headers = {'Authorization': f"Bearer {registered['access_token']}"}
        response = self.client.get('/api/config', headers=headers)
        self.assertEqual(response.json()['chat_question_limit'], settings.chat_question_limit)


if __name__ == '__main__':
    unittest.main()
