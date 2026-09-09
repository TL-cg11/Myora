import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
