import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_session
from app.main import app
from app.models import (
    AppUser,
    AppUserRole,
    Base,
    ChatRole,
    InterpretationSource,
    Reading,
    ReadingChatMessage,
    ReadingStatus,
    TarotChatMessage,
    TarotReading,
    Topic,
)


class ConversationApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        now = datetime(2026, 9, 11, 12, 0)
        with Session(self.engine) as session:
            session.add_all([
                AppUser(
                    id=1, username="owner", name="소유자", email="owner@example.com",
                    password_hash="x", role=AppUserRole.user,
                ),
                AppUser(
                    id=2, username="other", name="다른 사용자", email="other@example.com",
                    password_hash="x", role=AppUserRole.user,
                ),
                Reading(
                    id=11, service="saju", user_id=1, summary_title="사주 결과",
                    summary_text="사주 요약", status="interpreted", created_at=now,
                ),
                Reading(
                    id=12, service="face", user_id=2, summary_title="남의 관상",
                    summary_text="노출 금지", status="interpreted", created_at=now,
                ),
                Reading(
                    id=13, service="face", user_id=None, guest_key="guest",
                    summary_title="비회원 관상", status="interpreted", created_at=now,
                ),
                TarotReading(
                    id=21, user_id=1, spread_id=1, topic=Topic.general,
                    summary_title="타로 결과", summary_text="타로 요약",
                    interpretation_source=InterpretationSource.rule,
                    status=ReadingStatus.interpreted, created_at=now - timedelta(minutes=1),
                ),
                ReadingChatMessage(
                    id=101, reading_id=11, seq=1, role="user", content="용신이 뭐야?",
                    policy_version="1.1", created_at=now + timedelta(seconds=1),
                ),
                ReadingChatMessage(
                    id=102, reading_id=11, seq=2, role="assistant", content="용신 설명",
                    source="llm", policy_version="1.1", created_at=now + timedelta(seconds=2),
                ),
                ReadingChatMessage(
                    id=103, reading_id=11, seq=3, role="user", content="[검사 중인 질문]",
                    policy_version=None, created_at=now + timedelta(seconds=3),
                ),
                TarotChatMessage(
                    id=201, reading_id=21, seq=1, role=ChatRole.user,
                    content="카드 뜻은?", policy_version="1.1",
                    created_at=now + timedelta(seconds=4),
                ),
            ])
            session.commit()

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        self.owner = AppUser(id=1, role=AppUserRole.user)
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[current_user] = lambda: self.owner
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_list_merges_services_and_cursor_has_no_duplicates(self):
        first = self.client.get("/api/conversations", params={"limit": 1})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["items"][0]["service"], "saju")
        cursor = first.json()["next_cursor"]
        self.assertIsNotNone(cursor)

        second = self.client.get(
            "/api/conversations", params={"limit": 1, "cursor": cursor}
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["items"][0]["service"], "tarot")
        self.assertNotEqual(
            first.json()["items"][0]["reading_id"],
            second.json()["items"][0]["reading_id"],
        )

    def test_detail_groups_ordered_completed_messages(self):
        response = self.client.get("/api/conversations/saju/11")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["result"]["title"], "사주 결과")
        self.assertEqual([message["seq"] for message in body["messages"]], [1, 2])
        self.assertEqual(body["messages"][1]["source"], "llm")
        self.assertNotIn("검사 중", str(body))

    def test_empty_chat_is_returned_as_an_empty_list(self):
        with Session(self.engine) as session:
            session.add(Reading(
                id=14, service="face", user_id=1, summary_title="대화 없는 관상",
                status="interpreted", created_at=datetime(2026, 9, 10),
            ))
            session.commit()
        response = self.client.get("/api/conversations/face/14")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["messages"], [])

    def test_tarot_detail_uses_the_same_conversation_contract(self):
        response = self.client.get("/api/conversations/tarot/21")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["service"], "tarot")
        self.assertEqual(body["result"]["title"], "타로 결과")
        self.assertEqual(body["messages"][0]["content"], "카드 뜻은?")

    def test_other_member_and_guest_readings_are_both_404(self):
        for reading_id in (12, 13):
            response = self.client.get(f"/api/conversations/face/{reading_id}")
            self.assertEqual(response.status_code, 404)

    def test_invalid_cursor_is_400(self):
        response = self.client.get("/api/conversations", params={"cursor": "invalid"})
        self.assertEqual(response.status_code, 400)

    def test_authentication_is_required(self):
        del app.dependency_overrides[current_user]
        response = self.client.get("/api/conversations")
        self.assertEqual(response.status_code, 401)


class ConversationSameTimestampOrderingTests(unittest.TestCase):
    """생성 시각이 완전히 같은 리딩끼리도 순서가 안정적이고 페이지 사이에
    누락·중복이 없어야 한다. 서로 다른 시각만 다루는 위 테스트로는 이 경로가
    검증되지 않는다."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        now = datetime(2026, 9, 11, 12, 0)
        with Session(self.engine) as session:
            session.add_all([
                AppUser(
                    id=1, username="owner", name="소유자", email="owner@example.com",
                    password_hash="x", role=AppUserRole.user,
                ),
                # 같은 시각에 사주 2개 + 관상 1개 + 타로 2개. id는 일부러 뒤섞는다.
                Reading(id=50, service="saju", user_id=1, summary_title="사주A",
                        status="interpreted", created_at=now),
                Reading(id=30, service="saju", user_id=1, summary_title="사주B",
                        status="interpreted", created_at=now),
                Reading(id=40, service="face", user_id=1, summary_title="관상A",
                        status="interpreted", created_at=now),
                TarotReading(id=20, user_id=1, spread_id=1, topic=Topic.general,
                             summary_title="타로A", interpretation_source=InterpretationSource.rule,
                             status=ReadingStatus.interpreted, created_at=now),
                TarotReading(id=60, user_id=1, spread_id=1, topic=Topic.general,
                             summary_title="타로B", interpretation_source=InterpretationSource.rule,
                             status=ReadingStatus.interpreted, created_at=now),
            ])
            session.commit()

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[current_user] = lambda: AppUser(id=1, role=AppUserRole.user)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_paging_through_ties_has_no_gaps_or_duplicates(self):
        seen = []
        cursor = None
        for _ in range(10):
            response = self.client.get(
                "/api/conversations",
                params={"limit": 2, **({"cursor": cursor} if cursor else {})},
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            seen.extend((item["service"], item["reading_id"]) for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(set(seen)), 5, f"페이지 사이에 중복 발생: {seen}")
        # 서비스 랭크(사주 < 타로 < 관상) 오름차순, 같은 서비스 안에서는 id 내림차순.
        self.assertEqual(seen, [
            ("saju", 50), ("saju", 30),
            ("tarot", 60), ("tarot", 20),
            ("face", 40),
        ])


class ConversationSurvivesPolicyVersionBumpTests(unittest.TestCase):
    """'내 대화 다시 보기'는 사용자가 실제로 나눈 대화를 그대로 보여주는 화면이다.
    정책 버전이 올라갔다는 이유로 옛날 메시지가 안 보이면 안 된다. 그 필터는
    AI 문맥 조립(app/routers/chat.py 등)에만 남긴다."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        now = datetime(2026, 9, 11, 12, 0)
        with Session(self.engine) as session:
            session.add_all([
                AppUser(
                    id=1, username="owner", name="소유자", email="owner@example.com",
                    password_hash="x", role=AppUserRole.user,
                ),
                Reading(
                    id=15, service="saju", user_id=1, summary_title="옛 정책 사주",
                    summary_text="요약", status="interpreted", created_at=now,
                ),
                # 지금 POLICY_VERSION과 다른, 지난 정책으로 완료된 실제 대화.
                ReadingChatMessage(
                    id=111, reading_id=15, seq=1, role="user", content="옛날 질문",
                    policy_version="0.9", created_at=now + timedelta(seconds=1),
                ),
                ReadingChatMessage(
                    id=112, reading_id=15, seq=2, role="assistant", content="옛날 답변",
                    source="llm", policy_version="0.9", created_at=now + timedelta(seconds=2),
                ),
                # 정책 버전과 무관하게 이건 계속 숨겨져야 한다.
                ReadingChatMessage(
                    id=113, reading_id=15, seq=3, role="user", content="[검사 중인 질문]",
                    policy_version=None, created_at=now + timedelta(seconds=3),
                ),
            ])
            session.commit()

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[current_user] = lambda: AppUser(id=1, role=AppUserRole.user)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_older_policy_version_messages_still_appear(self):
        response = self.client.get("/api/conversations/saju/15")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([m["seq"] for m in body["messages"]], [1, 2])
        self.assertEqual(body["message_count"], 2)
        self.assertNotIn("검사 중", str(body))

    def test_list_counts_older_policy_version_messages_too(self):
        response = self.client.get("/api/conversations", params={"service": "saju"})
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["items"][0]
        self.assertEqual(item["message_count"], 2)


if __name__ == "__main__":
    unittest.main()
