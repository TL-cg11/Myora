import hashlib
import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.routers.security_events import router
from app.security_auth import SecurityAuthMiddleware, TokenAuthenticator
from app.security_db import get_security_session
from app.security_event_actions import ALLOWED_STATUS_TRANSITIONS
from app.security_models import (
    SecurityBase,
    SecurityEvent,
    SecurityEventAction,
    SecurityEventStatus,
    SecurityRiskLevel,
    SecurityRole,
    SecurityUser,
    SecurityUserStatus,
)


TOKEN = "security-editor-token"


def event(database_id: int, event_id: str, event_status: SecurityEventStatus):
    timestamp = datetime(2026, 9, 8, 10, 0)
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
        event_name="test-event",
        risk_level=SecurityRiskLevel.HIGH,
        risk_score=80,
        detector_version="1.0.0",
        masking_policy_version="1.0.0",
        status=event_status,
        resolution_reason=(
            "previous resolution"
            if event_status in {
                SecurityEventStatus.RESOLVED,
                SecurityEventStatus.FALSE_POSITIVE,
            }
            else None
        ),
        resolved_at=(
            timestamp
            if event_status in {
                SecurityEventStatus.RESOLVED,
                SecurityEventStatus.FALSE_POSITIVE,
            }
            else None
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


class SecurityEventActionTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SecurityBase.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        with self.SessionLocal() as session:
            session.add_all(
                [
                    event(1, "evt-open", SecurityEventStatus.OPEN),
                    event(2, "evt-investigating", SecurityEventStatus.INVESTIGATING),
                    event(3, "evt-resolved", SecurityEventStatus.RESOLVED),
                    event(4, "evt-false-positive", SecurityEventStatus.FALSE_POSITIVE),
                    SecurityUser(
                        id=1,
                        actor_id="assignee-a",
                        display_name="Assignee A",
                        status=SecurityUserStatus.ACTIVE,
                    ),
                    SecurityUser(
                        id=2,
                        actor_id="disabled-a",
                        display_name="Disabled A",
                        status=SecurityUserStatus.DISABLED,
                    ),
                ]
            )
            session.commit()

        self.auth_user = SecurityUser(
            actor_id="editor-a",
            display_name="Editor A",
            status=SecurityUserStatus.ACTIVE,
        )
        self.auth_user.roles = [SecurityRole(role_code="EDITOR")]
        token_hash = hashlib.sha256(TOKEN.encode()).hexdigest()
        app = FastAPI()
        app.add_middleware(
            SecurityAuthMiddleware,
            authenticator=TokenAuthenticator(
                {token_hash: "editor-a"}, lambda _actor_id: self.auth_user
            ),
        )
        app.include_router(router)

        def session_override():
            with self.SessionLocal() as session:
                yield session

        app.dependency_overrides[get_security_session] = session_override
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {TOKEN}"}

    def test_transition_matrix_matches_plan(self) -> None:
        self.assertEqual(
            ALLOWED_STATUS_TRANSITIONS,
            {
                (SecurityEventStatus.OPEN, SecurityEventStatus.INVESTIGATING),
                (SecurityEventStatus.OPEN, SecurityEventStatus.FALSE_POSITIVE),
                (SecurityEventStatus.INVESTIGATING, SecurityEventStatus.RESOLVED),
                (
                    SecurityEventStatus.INVESTIGATING,
                    SecurityEventStatus.FALSE_POSITIVE,
                ),
                (SecurityEventStatus.RESOLVED, SecurityEventStatus.OPEN),
                (SecurityEventStatus.FALSE_POSITIVE, SecurityEventStatus.OPEN),
            },
        )

    def test_status_changes_create_append_only_actions_with_actor(self) -> None:
        first = self.client.patch(
            "/api/security/events/evt-open/status",
            json={"status": "INVESTIGATING", "reason": "triage started"},
            headers=self.headers,
        )
        second = self.client.patch(
            "/api/security/events/evt-open/status",
            json={"status": "RESOLVED", "reason": "verified and blocked"},
            headers=self.headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "RESOLVED")
        self.assertIsNotNone(second.json()["resolved_at"])
        self.assertEqual(
            [action["action_type"] for action in second.json()["actions"]],
            ["STATUS_CHANGED", "RESOLVED"],
        )
        self.assertTrue(
            all(action["actor_id"] == "editor-a" for action in second.json()["actions"])
        )

    def test_invalid_transition_rolls_back_without_action(self) -> None:
        response = self.client.patch(
            "/api/security/events/evt-open/status",
            json={"status": "RESOLVED"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 409)
        with self.SessionLocal() as session:
            stored = session.get(SecurityEvent, 1)
            action_count = session.scalar(select(func.count(SecurityEventAction.id)))
            self.assertEqual(stored.status, SecurityEventStatus.OPEN)
            self.assertEqual(action_count, 0)

    def test_assignment_requires_active_user_and_records_assigned(self) -> None:
        disabled = self.client.patch(
            "/api/security/events/evt-open/assignee",
            json={"assigned_to": "disabled-a"},
            headers=self.headers,
        )
        spoofed = self.client.patch(
            "/api/security/events/evt-open/assignee",
            json={"assigned_to": "assignee-a", "actor_id": "spoofed"},
            headers=self.headers,
        )
        assigned = self.client.patch(
            "/api/security/events/evt-open/assignee",
            json={"assigned_to": "assignee-a"},
            headers=self.headers,
        )

        self.assertEqual(disabled.status_code, 404)
        self.assertEqual(spoofed.status_code, 422)
        self.assertEqual(assigned.status_code, 200)
        body = assigned.json()
        self.assertEqual(body["assigned_to"], "assignee-a")
        self.assertEqual(body["actions"][-1]["action_type"], "ASSIGNED")
        self.assertEqual(body["actions"][-1]["actor_id"], "editor-a")

    def test_false_positive_and_reopen_preserve_reasons_in_actions(self) -> None:
        marked = self.client.post(
            "/api/security/events/evt-open/false-positive",
            json={"resolution_reason": "approved synthetic fixture"},
            headers=self.headers,
        )
        reopened = self.client.post(
            "/api/security/events/evt-open/reopen",
            json={"reason": "new evidence"},
            headers=self.headers,
        )

        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json()["status"], "FALSE_POSITIVE")
        self.assertEqual(marked.json()["resolution_reason"], "approved synthetic fixture")
        self.assertEqual(reopened.status_code, 200)
        body = reopened.json()
        self.assertEqual(body["status"], "OPEN")
        self.assertIsNone(body["resolution_reason"])
        self.assertIsNone(body["resolved_at"])
        self.assertEqual(
            [action["action_type"] for action in body["actions"]],
            ["MARKED_FALSE_POSITIVE", "REOPENED"],
        )
        self.assertEqual(body["actions"][0]["reason"], "approved synthetic fixture")

    def test_remaining_planned_transitions_use_dedicated_endpoints(self) -> None:
        marked = self.client.post(
            "/api/security/events/evt-investigating/false-positive",
            json={"resolution_reason": "investigation confirmed fixture"},
            headers=self.headers,
        )
        reopened = self.client.post(
            "/api/security/events/evt-resolved/reopen",
            json={"reason": "recurrence detected"},
            headers=self.headers,
        )
        bypass = self.client.patch(
            "/api/security/events/evt-false-positive/status",
            json={"status": "OPEN"},
            headers=self.headers,
        )

        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json()["status"], "FALSE_POSITIVE")
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["status"], "OPEN")
        self.assertEqual(bypass.status_code, 409)

    def test_viewer_cannot_mutate_events(self) -> None:
        self.auth_user.roles = [SecurityRole(role_code="VIEWER")]
        response = self.client.patch(
            "/api/security/events/evt-open/status",
            json={"status": "INVESTIGATING"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
