import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.local_db import initialize
from app.main import app
from app.models import AppUser, AppUserRole, AuthIpLockout, AuthSession, Reading
from app.routers import auth as auth_router


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
        self.assertEqual(result["user"]["role"], "user")
        headers = {"Authorization": f"Bearer {result['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "user")
        with Session(self.engine) as session:
            user = session.scalar(select(AppUser))
            self.assertNotEqual(user.password_hash, "safe-password-123")
            self.assertTrue(user.password_hash.startswith("pbkdf2_sha256$"))
            self.assertEqual(session.query(AuthSession).count(), 1)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_login_and_me_return_the_current_database_role(self):
        registered = self.register()
        with Session(self.engine) as session:
            session.execute(
                update(AppUser)
                .where(AppUser.username == "myohan_user")
                .values(role=AppUserRole.admin)
            )
            session.commit()
        login = self.client.post(
            "/api/auth/login",
            json={"login_id": "myohan_user", "password": "safe-password-123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["role"], "admin")
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["role"], "admin")

    def test_register_ignores_role_field_in_request(self):
        """RegisterIn에 role 필드가 없어 무시되지만, 필드가 추가되는 순간 셀프
        관리자 승격이 될 수 있다. 그 회귀를 여기서 잡는다."""
        response = self.client.post(
            "/api/auth/register",
            json={
                "username": "sneaky_user",
                "name": "테스트",
                "password": "safe-password-123",
                "email": "sneaky@example.com",
                "guest_key": str(uuid4()),
                "role": "admin",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user"]["role"], "user")

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

    def test_five_consecutive_failures_lock_ip_for_one_hour(self):
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
        self.assertEqual(existing_session.status_code, 200)
        with Session(self.engine) as session:
            self.assertEqual(session.query(AuthSession).count(), 1)
            lockout = session.scalar(select(AuthIpLockout))
            self.assertEqual(lockout.failed_login_attempts, 5)
            self.assertIsNotNone(lockout.locked_until)

    def test_ip_lock_applies_across_accounts_without_locking_other_ip(self):
        self.register()
        self.register("second_user", "second@example.com")
        policy = SimpleNamespace(
            auth_trusted_proxy_ips=("testclient",),
            auth_ip_max_failed_attempts=5,
            auth_ip_lockout_minutes=60,
        )

        with patch.object(auth_router, "settings", policy):
            blocked_headers = {"X-Real-IP": "203.0.113.10"}
            for attempt in range(1, 6):
                response = self.client.post(
                    "/api/auth/login",
                    headers=blocked_headers,
                    json={"login_id": f"unknown-{attempt}", "password": "wrong"},
                )
                self.assertEqual(response.status_code, 429 if attempt == 5 else 401)

            blocked = self.client.post(
                "/api/auth/login",
                headers=blocked_headers,
                json={"login_id": "second_user", "password": "safe-password-123"},
            )
            self.assertEqual(blocked.status_code, 429)

            allowed = self.client.post(
                "/api/auth/login",
                headers={"X-Real-IP": "203.0.113.11"},
                json={"login_id": "second_user", "password": "safe-password-123"},
            )
            self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_legacy_account_lock_no_longer_blocks_login(self):
        self.register()
        with Session(self.engine) as session:
            user = session.scalar(select(AppUser))
            user.failed_login_attempts = 5
            user.locked_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
            session.commit()

        response = self.client.post(
            "/api/auth/login",
            json={"login_id": "myohan_user", "password": "safe-password-123"},
        )

        self.assertEqual(response.status_code, 200, response.text)

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
            self.assertEqual(session.query(AuthIpLockout).count(), 0)

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
