import hashlib
import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.routers.security_audit import router as audit_router
from app.routers.security_events import router as events_router
from app.security_auth import SecurityAuthMiddleware, TokenAuthenticator
from app.security_db import get_security_session
from app.security_models import (
    SecurityActionType,
    SecurityActorType,
    SecurityBase,
    SecurityEvent,
    SecurityEventAction,
    SecurityEventStatus,
    SecurityRiskLevel,
    SecurityRole,
    SecurityUser,
    SecurityUserStatus,
)


TOKEN = "security-audit-token"


def make_event(database_id: int, event_id: str) -> SecurityEvent:
    timestamp = datetime(2026, 9, 8, 9, 0)
    return SecurityEvent(
        id=database_id,
        event_id=event_id,
        source_event_id=f"source-{event_id}",
        schema_version="1.0",
        occurred_at=timestamp,
        detected_at=timestamp,
        environment="test",
        source_service="luck-was",
        source_type="application-log",
        event_name="audit-test",
        risk_level=SecurityRiskLevel.HIGH,
        risk_score=80,
        detector_version="1.0.0",
        masking_policy_version="1.0.0",
        status=SecurityEventStatus.OPEN,
        created_at=timestamp,
        updated_at=timestamp,
    )


class SecurityAuditApiTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SecurityBase.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        with self.SessionLocal() as session:
            session.add_all([make_event(1, "evt-a"), make_event(2, "evt-b")])
            session.flush()
            session.add_all(
                [
                    SecurityEventAction(
                        id=1,
                        security_event_id=1,
                        action_type=SecurityActionType.CREATED,
                        actor_type=SecurityActorType.SYSTEM,
                        actor_id="security-event-sink",
                        new_status="OPEN",
                        acted_at=datetime(2026, 9, 8, 9, 0),
                    ),
                    SecurityEventAction(
                        id=2,
                        security_event_id=1,
                        action_type=SecurityActionType.ASSIGNED,
                        actor_type=SecurityActorType.USER,
                        actor_id="editor-a",
                        new_assignee="editor-a",
                        acted_at=datetime(2026, 9, 8, 10, 0),
                    ),
                    SecurityEventAction(
                        id=3,
                        security_event_id=2,
                        action_type=SecurityActionType.REOPENED,
                        actor_type=SecurityActorType.USER,
                        actor_id="admin-a",
                        previous_status="RESOLVED",
                        new_status="OPEN",
                        reason="new evidence",
                        acted_at=datetime(2026, 9, 8, 11, 0),
                    ),
                ]
            )
            session.commit()

        self.auth_user = SecurityUser(
            actor_id="operator-a",
            display_name="Operator A",
            status=SecurityUserStatus.ACTIVE,
        )
        self.set_role("VIEWER")
        token_hash = hashlib.sha256(TOKEN.encode()).hexdigest()
        app = FastAPI()
        app.add_middleware(
            SecurityAuthMiddleware,
            authenticator=TokenAuthenticator(
                {token_hash: "operator-a"}, lambda _actor_id: self.auth_user
            ),
        )
        app.include_router(audit_router)
        app.include_router(events_router)

        def session_override():
            with self.SessionLocal() as session:
                yield session

        app.dependency_overrides[get_security_session] = session_override
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {TOKEN}"}

    def set_role(self, role_code: str) -> None:
        self.auth_user.roles = [SecurityRole(role_code=role_code)]

    def action_count(self) -> int:
        with self.SessionLocal() as session:
            return session.scalar(select(func.count(SecurityEventAction.id))) or 0

    def test_audit_list_is_sorted_and_paginated(self) -> None:
        response = self.client.get(
            "/api/security/audit-logs",
            params={"page": 1, "page_size": 2},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual(
            [item["action_type"] for item in body["items"]],
            ["REOPENED", "ASSIGNED"],
        )
        self.assertNotIn("security_event_id", str(body))

    def test_audit_filters_are_combined(self) -> None:
        response = self.client.get(
            "/api/security/audit-logs",
            params={
                "start_time": "2026-09-08T09:30:00Z",
                "end_time": "2026-09-08T10:30:00Z",
                "event_id": "evt-a",
                "actor_id": "editor-a",
                "action_type": "ASSIGNED",
                "sort_order": "asc",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["event_id"], "evt-a")

    def test_invalid_period_is_rejected(self) -> None:
        response = self.client.get(
            "/api/security/audit-logs",
            params={
                "start_time": "2026-09-09T00:00:00Z",
                "end_time": "2026-09-08T00:00:00Z",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 422)

    def test_audit_mutation_is_always_method_not_allowed(self) -> None:
        before = self.action_count()
        responses = [
            self.client.post(
                "/api/security/audit-logs", json={}, headers=self.headers
            ),
            self.client.patch(
                "/api/security/audit-logs/1", json={}, headers=self.headers
            ),
            self.client.delete("/api/security/audit-logs/1", headers=self.headers),
        ]

        self.assertTrue(all(response.status_code == 405 for response in responses))
        self.assertEqual(self.action_count(), before)

    def test_viewer_editor_admin_permission_flow(self) -> None:
        self.assertEqual(
            self.client.get("/api/security/events", headers=self.headers).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/security/audit-logs", headers=self.headers).status_code,
            200,
        )
        viewer_change = self.client.patch(
            "/api/security/events/evt-a/status",
            json={"status": "INVESTIGATING"},
            headers=self.headers,
        )
        self.assertEqual(viewer_change.status_code, 403)

        self.set_role("EDITOR")
        editor_change = self.client.patch(
            "/api/security/events/evt-a/status",
            json={"status": "INVESTIGATING"},
            headers=self.headers,
        )
        self.assertEqual(editor_change.status_code, 200)

        self.set_role("ADMIN")
        admin_change = self.client.patch(
            "/api/security/events/evt-a/status",
            json={"status": "RESOLVED"},
            headers=self.headers,
        )
        self.assertEqual(admin_change.status_code, 200)
        audit = self.client.get("/api/security/audit-logs", headers=self.headers)
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(audit.json()["total"], 5)

    def test_unauthenticated_audit_access_is_rejected(self) -> None:
        response = self.client.get("/api/security/audit-logs")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
