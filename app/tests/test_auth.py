import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.local_db import initialize
from app.main import app
from app.models import AppUser, AuthSession, Reading


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        initialize(self.engine)

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def register(self, username="myohan_user", email="user@example.com", guest_key=None):
        response = self.client.post(
            "/api/auth/register",
            json={
                "username": username,
                "name": "묘한 사용자",
                "password": "safe-password-123",
                "email": email,
                "guest_key": str(guest_key or uuid4()),
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_register_me_logout_and_password_is_hashed(self):
        result = self.register()
        headers = {"Authorization": f"Bearer {result['access_token']}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        with Session(self.engine) as session:
            user = session.scalar(select(AppUser))
            self.assertNotEqual(user.password_hash, "safe-password-123")
            self.assertTrue(user.password_hash.startswith("pbkdf2_sha256$"))
            self.assertEqual(session.query(AuthSession).count(), 1)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_duplicate_and_wrong_password_are_rejected(self):
        self.register()
        duplicate = self.client.post(
            "/api/auth/register",
            json={"username": "myohan_user", "name": "다른 이름", "password": "another-pass", "email": "other@example.com"},
        )
        self.assertEqual(duplicate.status_code, 409)
        wrong = self.client.post(
            "/api/auth/login", json={"login_id": "myohan_user", "password": "wrong"}
        )
        self.assertEqual(wrong.status_code, 401)

    def test_five_consecutive_failures_lock_account_for_one_hour(self):
        registered = self.register()
        for attempt in range(1, 6):
            response = self.client.post(
                "/api/auth/login",
                json={"login_id": "myohan_user", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 429 if attempt == 5 else 401)
        locked = self.client.post(
            "/api/auth/login",
            json={"login_id": "myohan_user", "password": "safe-password-123"},
        )
        self.assertEqual(locked.status_code, 429)
        self.assertGreaterEqual(int(locked.headers["Retry-After"]), 3500)
        existing_session = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        self.assertEqual(existing_session.status_code, 401)
        with Session(self.engine) as session:
            self.assertEqual(session.query(AuthSession).count(), 0)

    def test_success_resets_failures_and_session_expires_in_one_hour(self):
        self.register()
        for _ in range(4):
            self.client.post(
                "/api/auth/login",
                json={"login_id": "myohan_user", "password": "wrong-password"},
            )
        before = datetime.now(UTC).replace(tzinfo=None)
        response = self.client.post(
            "/api/auth/login",
            json={"login_id": "myohan_user", "password": "safe-password-123"},
        )
        self.assertEqual(response.status_code, 200)
        expires_at = datetime.fromisoformat(response.json()["expires_at"])
        self.assertTrue(before + timedelta(minutes=59) <= expires_at <= before + timedelta(minutes=61))
        with Session(self.engine) as session:
            user = session.scalar(select(AppUser))
            self.assertEqual(user.failed_login_attempts, 0)
            self.assertIsNone(user.locked_until)

    def test_server_rejects_session_older_than_one_hour(self):
        result = self.register()
        with Session(self.engine) as session:
            session.execute(
                update(AuthSession).values(
                    created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
                    expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
                )
            )
            session.commit()
        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {result['access_token']}"},
        )
        self.assertEqual(response.status_code, 401)

    def test_guest_reading_is_claimed_and_other_user_cannot_list_it(self):
        guest_key = uuid4()
        with Session(self.engine) as session:
            session.add(Reading(service="saju", guest_key=str(guest_key), summary_title="내 기록", status="interpreted"))
            session.commit()
        first = self.register(guest_key=guest_key)
        first_headers = {"Authorization": f"Bearer {first['access_token']}"}
        first_list = self.client.get(f"/api/saju/readings?guest_key={uuid4()}", headers=first_headers)
        self.assertEqual(len(first_list.json()), 1)

        second = self.register("second_user", "second@example.com")
        second_headers = {"Authorization": f"Bearer {second['access_token']}"}
        second_list = self.client.get(f"/api/saju/readings?guest_key={guest_key}", headers=second_headers)
        self.assertEqual(second_list.json(), [])


if __name__ == "__main__":
    unittest.main()
