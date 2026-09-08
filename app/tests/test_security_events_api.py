import hashlib
import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.routers.security_events import router
from app.security_auth import SecurityAuthMiddleware, TokenAuthenticator
from app.security_db import get_security_session
from app.security_models import (
    SecurityActionType,
    SecurityActorType,
    SecurityBase,
    SecurityEvent,
    SecurityEventAction,
    SecurityEventDetection,
    SecurityEventStatus,
    SecurityRiskLevel,
    SecurityRole,
    SecurityUser,
    SecurityUserStatus,
)


TOKEN = "security-api-test-token"


def make_event(
    database_id: int,
    event_id: str,
    detected_at: datetime,
    risk_level: SecurityRiskLevel,
    risk_score: int,
    source_service: str,
    source_type: str,
) -> SecurityEvent:
    return SecurityEvent(
        id=database_id,
        event_id=event_id,
        source_event_id=f"source-{event_id}",
        request_id=f"request-{event_id}",
        schema_version="1.0",
        occurred_at=detected_at,
        detected_at=detected_at,
        environment="test",
        source_service=source_service,
        source_type=source_type,
        event_name="sensitive-data-detected",
        risk_level=risk_level,
        risk_score=risk_score,
        detector_version="1.0.0",
        masking_policy_version="1.0.0",
        masked_excerpt="email=***",
        body_hash=f"sha256:{event_id}",
        status=SecurityEventStatus.OPEN,
        safe_metadata={"method": "POST"},
        created_at=detected_at,
        updated_at=detected_at,
    )


class SecurityEventsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SecurityBase.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

        first = make_event(
            1,
            "evt-high",
            datetime(2026, 9, 2, 12, 0),
            SecurityRiskLevel.HIGH,
            80,
            "nginx",
            "access-log",
        )
        first.detections.append(
            SecurityEventDetection(
                id=1,
                detection_id="det-1",
                rule_id="email",
                rule_version="1",
                category="PII",
                entity_type="EMAIL",
                risk_level=SecurityRiskLevel.HIGH,
                confidence=0.98,
                match_count=1,
                evidence_fingerprint="fingerprint",
                locations_json=[{"field": "message"}],
                created_at=datetime(2026, 9, 2, 12, 0),
            )
        )
        first.actions.append(
            SecurityEventAction(
                id=1,
                action_type=SecurityActionType.CREATED,
                actor_type=SecurityActorType.SYSTEM,
                actor_id="security-event-sink",
                new_status="OPEN",
                acted_at=datetime(2026, 9, 2, 12, 0),
            )
        )
        events = [
            first,
            make_event(
                2,
                "evt-low",
                datetime(2026, 9, 1, 12, 0),
                SecurityRiskLevel.LOW,
                20,
                "luck-was",
                "application-log",
            ),
            make_event(
                3,
                "evt-critical",
                datetime(2026, 9, 3, 12, 0),
                SecurityRiskLevel.CRITICAL,
                99,
                "mariadb",
                "database-log",
            ),
        ]
        with self.SessionLocal() as session:
            session.add_all(events)
            session.commit()

        user = SecurityUser(
            actor_id="viewer-a",
            display_name="Viewer A",
            status=SecurityUserStatus.ACTIVE,
        )
        user.roles = [SecurityRole(role_code="VIEWER")]
        token_hash = hashlib.sha256(TOKEN.encode()).hexdigest()
        app = FastAPI()
        app.add_middleware(
            SecurityAuthMiddleware,
            authenticator=TokenAuthenticator(
                {token_hash: "viewer-a"}, lambda _actor_id: user
            ),
        )
        app.include_router(router)

        def session_override():
            with self.SessionLocal() as session:
                yield session

        app.dependency_overrides[get_security_session] = session_override
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {TOKEN}"}

    def test_list_is_sorted_and_paginated(self) -> None:
        response = self.client.get(
            "/api/security/events",
            params={"page": 1, "page_size": 2},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual(
            [item["event_id"] for item in body["items"]],
            ["evt-critical", "evt-high"],
        )

    def test_list_applies_period_risk_status_source_and_sort(self) -> None:
        response = self.client.get(
            "/api/security/events",
            params={
                "start_time": "2026-09-02T00:00:00Z",
                "end_time": "2026-09-02T23:59:59Z",
                "risk_level": "HIGH",
                "status": "OPEN",
                "source": "access-log",
                "sort_by": "risk_score",
                "sort_order": "asc",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["event_id"], "evt-high")

    def test_invalid_period_and_sort_are_rejected(self) -> None:
        period_response = self.client.get(
            "/api/security/events",
            params={
                "start_time": "2026-09-03T00:00:00Z",
                "end_time": "2026-09-02T00:00:00Z",
            },
            headers=self.headers,
        )
        sort_response = self.client.get(
            "/api/security/events",
            params={"sort_by": "event_id; DROP TABLE security_event"},
            headers=self.headers,
        )

        self.assertEqual(period_response.status_code, 422)
        self.assertEqual(sort_response.status_code, 422)

    def test_detail_contains_detections_and_actions(self) -> None:
        response = self.client.get(
            "/api/security/events/evt-high", headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["detections"][0]["detection_id"], "det-1")
        self.assertEqual(body["actions"][0]["action_type"], "CREATED")
        self.assertNotIn("id", body)
        self.assertNotIn("security_event_id", str(body))

    def test_unknown_event_returns_not_found(self) -> None:
        response = self.client.get(
            "/api/security/events/evt-missing", headers=self.headers
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
