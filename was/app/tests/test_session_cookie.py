"""Bearer 토큰과 함께 쓰는 cookie 세션, 그리고 nginx auth_request용
관리자 검증 endpoint(/api/auth/admin-check)를 검증한다.

Grafana iframe처럼 nginx auth_request가 대신 호출하는 경로는 원래 요청의
Authorization 헤더를 넘겨받지 않는다고 가정한다. 그래서 이 endpoint가 실제로
쓰이는 방식은 cookie뿐이고, 여기 테스트도 그 경로를 기준으로 삼는다.
"""

import unittest
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE_NAME, token_digest, utc_now
from app.db import get_session
from app.local_db import initialize
from app.main import app
from app.models import AppUser, AppUserRole, AuthSession


class SessionCookieTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        initialize(self.engine)

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app, base_url="https://testserver")

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def register(self, username="cookie_user", email="cookie@example.com", role=None):
        response = self.client.post("/api/auth/register", json={
            "username": username, "name": "쿠키 사용자", "password": "safe-password-123",
            "email": email, "guest_key": str(uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        if role is not None:
            with Session(self.engine) as session:
                session.execute(
                    update(AppUser).where(AppUser.username == username).values(role=role)
                )
                session.commit()
        return response

    def test_register_sets_httponly_secure_samesite_cookie(self):
        response = self.register()
        set_cookie = response.headers.get("set-cookie")
        self.assertIsNotNone(set_cookie)
        self.assertIn(f"{SESSION_COOKIE_NAME}=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIn("SameSite", set_cookie)

    def test_login_also_sets_the_cookie(self):
        self.register()
        response = self.client.post("/api/auth/login", json={
            "login_id": "cookie_user", "password": "safe-password-123",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(SESSION_COOKIE_NAME, response.cookies)

    def test_cookie_alone_authenticates_without_authorization_header(self):
        """Authorization 헤더를 아예 안 보내도 cookie만으로 통과해야 한다.

        nginx auth_request 경로가 실제로 이렇게 동작한다.
        """
        self.register()
        # TestClient가 register() 응답의 Set-Cookie를 세션에 반영해 뒀으므로
        # 이후 요청은 별도 헤더 없이도 그 cookie를 함께 보낸다.
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["username"], "cookie_user")

    def test_logout_clears_the_cookie_and_the_db_session(self):
        self.register()
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 200, response.text)
        set_cookie = response.headers.get("set-cookie")
        self.assertIsNotNone(set_cookie)
        self.assertIn(f"{SESSION_COOKIE_NAME}=", set_cookie)
        self.assertTrue(
            "Max-Age=0" in set_cookie or "01 Jan 1970" in set_cookie,
            set_cookie,
        )
        # 쿠키만으로도 더는 인증되지 않는다(DB 세션이 지워졌으므로).
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_expired_session_clears_the_stale_cookie_on_401(self):
        """세션이 만료된 순간에도 브라우저에 남은 cookie를 지운다.

        의존성 안에서 처리하면 예외로 빠지며 헤더 변경이 버려지므로
        미들웨어(app/main.py의 expire_stale_session_cookie)가 대신 한다.
        """
        self.register()
        with Session(self.engine) as session:
            user = session.query(AppUser).filter_by(username="cookie_user").one()
            token = "expired-raw-token"
            session.add(AuthSession(
                user_id=user.id, token_hash=token_digest(token),
                expires_at=utc_now() - timedelta(minutes=1),
            ))
            session.commit()
        self.client.cookies.set(SESSION_COOKIE_NAME, token)
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        set_cookie = response.headers.get("set-cookie")
        self.assertIsNotNone(set_cookie)
        self.assertIn(f"{SESSION_COOKIE_NAME}=", set_cookie)


class AdminCheckEndpointTests(unittest.TestCase):
    """/api/auth/admin-check: nginx auth_request가 그대로 status_code만 본다."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        initialize(self.engine)

        def session_override():
            with Session(self.engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app, base_url="https://testserver")

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def register(self, username, role):
        response = self.client.post("/api/auth/register", json={
            "username": username, "name": "테스트", "password": "safe-password-123",
            "email": f"{username}@example.com", "guest_key": str(uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        with Session(self.engine) as session:
            session.execute(update(AppUser).where(AppUser.username == username).values(role=role))
            session.commit()
        return response

    def test_unauthenticated_is_401(self):
        response = self.client.get("/api/auth/admin-check")
        self.assertEqual(response.status_code, 401)

    def test_regular_account_is_403_via_cookie_only(self):
        self.register("plain_user", AppUserRole.user)
        # Authorization 헤더 없이 cookie만으로 호출 — nginx auth_request와 같은 경로.
        response = self.client.get("/api/auth/admin-check")
        self.assertEqual(response.status_code, 403)

    def test_admin_account_is_2xx_via_cookie_only(self):
        self.register("admin_user", AppUserRole.admin)
        response = self.client.get("/api/auth/admin-check")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("x-auth-request-user"), "admin_user")

    def test_admin_via_bearer_header_also_passes(self):
        """직접 curl로 확인할 때 Authorization으로도 되는지."""
        response = self.register("admin_user2", AppUserRole.admin)
        token = response.json()["access_token"]
        self.client.cookies.clear()
        result = self.client.get(
            "/api/auth/admin-check", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(result.status_code, 204)


if __name__ == "__main__":
    unittest.main()
