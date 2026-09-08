import hashlib
import unittest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.security_auth import (
    Permission,
    ROLE_PERMISSIONS,
    SecurityAuthMiddleware,
    SecurityPrincipal,
    TokenAuthenticator,
    parse_token_hashes,
    require_permissions,
)
from app.security_models import SecurityRole, SecurityRoleCode, SecurityUser, SecurityUserStatus


def make_user(role_code: SecurityRoleCode, status=SecurityUserStatus.ACTIVE) -> SecurityUser:
    user = SecurityUser(actor_id="operator-a", display_name="Operator A", status=status)
    user.roles = [SecurityRole(role_code=role_code.value)]
    return user


def make_client(role_code: SecurityRoleCode, status=SecurityUserStatus.ACTIVE) -> TestClient:
    token = "test-secret-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    authenticator = TokenAuthenticator(
        {token_hash: "operator-a"}, lambda _actor_id: make_user(role_code, status)
    )
    app = FastAPI()
    app.add_middleware(SecurityAuthMiddleware, authenticator=authenticator)

    @app.get("/api/security/events")
    def read_events(
        principal: SecurityPrincipal = Depends(require_permissions(Permission.EVENT_READ)),
    ):
        return {"actor_id": principal.actor_id}

    @app.post("/api/security/users")
    def manage_users(
        _principal: SecurityPrincipal = Depends(require_permissions(Permission.USER_MANAGE)),
    ):
        return {"ok": True}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return TestClient(app)


class SecurityModelTests(unittest.TestCase):
    def test_user_role_mapping_matches_migration_tables(self) -> None:
        self.assertEqual(SecurityUser.__tablename__, "security_user")
        self.assertEqual(SecurityRole.__tablename__, "security_role")
        self.assertIn("security_user_role", SecurityUser.metadata.tables)


class PermissionMatrixTests(unittest.TestCase):
    def test_roles_are_cumulative(self) -> None:
        self.assertLess(
            ROLE_PERMISSIONS[SecurityRoleCode.VIEWER],
            ROLE_PERMISSIONS[SecurityRoleCode.EDITOR],
        )
        self.assertLess(
            ROLE_PERMISSIONS[SecurityRoleCode.EDITOR],
            ROLE_PERMISSIONS[SecurityRoleCode.ADMIN],
        )

    def test_invalid_hash_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_token_hashes('{"not-a-hash":"operator-a"}')


class SecurityMiddlewareTests(unittest.TestCase):
    def test_missing_and_invalid_tokens_are_rejected(self) -> None:
        client = make_client(SecurityRoleCode.VIEWER)
        self.assertEqual(client.get("/api/security/events").status_code, 401)
        self.assertEqual(
            client.get(
                "/api/security/events", headers={"Authorization": "Bearer wrong"}
            ).status_code,
            401,
        )

    def test_viewer_can_read_but_cannot_administer_users(self) -> None:
        client = make_client(SecurityRoleCode.VIEWER)
        headers = {"Authorization": "Bearer test-secret-token"}
        self.assertEqual(client.get("/api/security/events", headers=headers).status_code, 200)
        self.assertEqual(client.post("/api/security/users", headers=headers).status_code, 403)

    def test_admin_has_inherited_permissions(self) -> None:
        client = make_client(SecurityRoleCode.ADMIN)
        headers = {"Authorization": "Bearer test-secret-token"}
        self.assertEqual(client.get("/api/security/events", headers=headers).status_code, 200)
        self.assertEqual(client.post("/api/security/users", headers=headers).status_code, 200)

    def test_disabled_user_is_rejected(self) -> None:
        client = make_client(SecurityRoleCode.ADMIN, SecurityUserStatus.DISABLED)
        response = client.get(
            "/api/security/events",
            headers={"Authorization": "Bearer test-secret-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_non_security_api_is_not_affected(self) -> None:
        client = make_client(SecurityRoleCode.VIEWER)
        self.assertEqual(client.get("/api/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
