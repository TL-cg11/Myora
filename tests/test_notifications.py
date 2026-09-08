from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from security_sink.notification_policy import (
    NotificationPolicy,
    configured_channels,
    dedup_key,
    initial_alert_types,
    queue_rows,
)
from security_sink.notifications import (
    EmailSender,
    NotificationRepository,
    NotificationService,
    PendingNotification,
    SlackWebhookSender,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture() -> dict:
    return json.loads((ROOT / "fixtures" / "luck.security-events.normal.json").read_text(encoding="utf-8"))


def pending(identifier: int, channel: str = "SLACK", retry_count: int = 0) -> PendingNotification:
    return PendingNotification(
        identifier,
        f"event-{identifier}",
        "RISK_HIGH",
        channel,
        retry_count,
        "HIGH",
        "OPEN",
        "luck-was",
        "saju.chat.requested",
        datetime(2026, 9, 8, 0, 0),
        "email=[EMAIL] token=[API_KEY]",
    )


class FakeRepository:
    def __init__(self, items: list[PendingNotification]) -> None:
        self.items = items
        self.sent: list[int] = []
        self.failed: list[int] = []
        self.suppressed: list[int] = []

    def schedule_unresolved(self, now=None, limit=500):
        return 2

    def claim_due(self):
        return self.items

    def mark_sent(self, ids, sent_at=None):
        self.sent.extend(ids)

    def mark_failed(self, items, error):
        self.failed.extend(item.id for item in items)

    def mark_suppressed(self, ids, reason):
        self.suppressed.extend(ids)

class FakeSender:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.messages: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> None:
        self.messages.append((subject, body))
        if self.error:
            raise self.error


class FakeCursor:
    def __init__(self, rows=(), insert_rowcounts=()) -> None:
        self.rows = list(rows)
        self.insert_rowcounts = list(insert_rowcounts)
        self.executions = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, values):
        self.executions.append((sql, values))
        if "INSERT IGNORE INTO notification_log" in sql:
            self.rowcount = self.insert_rowcounts.pop(0) if self.insert_rowcounts else 1

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self):
        return None

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class NotificationPolicyTests(unittest.TestCase):
    def test_high_risk_and_repeated_behavior_create_both_alerts(self):
        self.assertEqual(
            initial_alert_types(fixture()),
            ("RISK_HIGH", "REPEATED_BEHAVIOR"),
        )

    def test_low_or_medium_non_repeated_event_does_not_alert_immediately(self):
        event = copy.deepcopy(fixture())
        event["risk_level"] = "MEDIUM"
        event["detections"][1]["match_count"] = 2
        self.assertEqual(initial_alert_types(event), ())

    def test_thresholds_and_retry_backoff_are_bounded(self):
        policy = NotificationPolicy()
        self.assertEqual(
            [policy.unresolved_hours(level) for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")],
            [1, 4, 24, 72],
        )
        self.assertEqual(policy.retry_delay(1), timedelta(seconds=60))
        self.assertEqual(policy.retry_delay(5), timedelta(seconds=960))
        self.assertEqual(policy.retry_delay(99), timedelta(seconds=3600))

    def test_dedup_key_is_event_alert_and_channel_based(self):
        self.assertEqual(
            dedup_key("event-1", "RISK_HIGH", "SLACK"),
            "event-1:RISK_HIGH:SLACK",
        )
        rows = queue_rows(fixture(), configured_channels("SLACK,EMAIL"))
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row[0] for row in rows}), 4)
        self.assertTrue(all(row[4] > datetime.utcnow() for row in rows))


class NotificationServiceTests(unittest.TestCase):
    def test_same_channel_notifications_are_grouped_into_one_delivery(self):
        repository = FakeRepository([pending(1), pending(2)])
        sender = FakeSender()
        result = NotificationService(repository, {"SLACK": sender}).run_once()

        self.assertEqual(result, {"scheduled": 2, "claimed": 2, "sent": 2, "failed": 0, "suppressed": 0})
        self.assertEqual(len(sender.messages), 1)
        self.assertEqual(repository.sent, [1, 2])

    def test_delivery_failure_is_recorded_for_retry(self):
        repository = FakeRepository([pending(1)])
        sender = FakeSender(RuntimeError("secret-bearing provider error"))
        result = NotificationService(repository, {"SLACK": sender}).run_once()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(repository.failed, [1])

    def test_disabled_channel_is_suppressed(self):
        repository = FakeRepository([pending(1, "EMAIL")])
        result = NotificationService(repository, {}).run_once()
        self.assertEqual(result["suppressed"], 1)
        self.assertEqual(repository.suppressed, [1])

    def test_unmasked_notification_is_suppressed_before_delivery(self):
        item = pending(1)
        unsafe = replace(item, masked_excerpt="user@example.com")
        repository = FakeRepository([unsafe])
        sender = FakeSender()
        result = NotificationService(repository, {"SLACK": sender}).run_once()

        self.assertEqual(result["suppressed"], 1)
        self.assertFalse(sender.messages)


class NotificationRepositoryTests(unittest.TestCase):
    def test_unresolved_scheduler_uses_risk_threshold_and_insert_ignore(self):
        now = datetime(2026, 9, 8, 12, 0)
        cursor = FakeCursor(
            rows=[
                ("critical-old", "CRITICAL", now - timedelta(hours=2)),
                ("high-young", "HIGH", now - timedelta(hours=2)),
            ],
            insert_rowcounts=[1, 0],
        )
        connection = FakeConnection(cursor)
        repository = NotificationRepository(
            lambda: connection, channels=("SLACK", "EMAIL")
        )

        inserted = repository.schedule_unresolved(now)

        self.assertEqual(inserted, 1)
        inserts = [entry for entry in cursor.executions if "INSERT IGNORE" in entry[0]]
        self.assertEqual(len(inserts), 2)
        self.assertTrue(all("LONG_UNRESOLVED_CRITICAL_1H" in values for _, values in inserts))
        self.assertTrue(connection.committed)

    def test_retry_state_uses_backoff_and_never_stores_provider_message(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        policy = NotificationPolicy(max_retries=2, retry_base_seconds=60)
        repository = NotificationRepository(
            lambda: connection, policy=policy, channels=("SLACK",)
        )

        repository.mark_failed([pending(1, retry_count=0)], RuntimeError("token=do-not-store"))
        values = cursor.executions[0][1]
        self.assertEqual(values[0], 1)
        self.assertIsNotNone(values[1])
        self.assertEqual(values[2], "RuntimeError: delivery failed")
        self.assertNotIn("do-not-store", str(values))

        cursor.executions.clear()
        repository.mark_failed([pending(1, retry_count=1)], RuntimeError("again"))
        self.assertIsNone(cursor.executions[0][1][1])


class DeliveryAdapterTests(unittest.TestCase):
    def test_slack_sender_posts_json_over_https(self):
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        def open_request(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        with patch("security_sink.notifications.urlopen", open_request):
            SlackWebhookSender("https://hooks.slack.test/services/mock").send("subject", "body")

        request = captured["request"]
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"text": "*subject*\nbody"})

    def test_email_sender_uses_starttls_login_and_recipients(self):
        calls = []

        class SMTP:
            def __init__(self, host, port, timeout):
                calls.append(("connect", host, port, timeout))

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def starttls(self, context):
                calls.append(("starttls", bool(context)))

            def login(self, username, password):
                calls.append(("login", username, password))

            def send_message(self, message):
                calls.append(("send", message["From"], message["To"], message.get_content().strip()))

        with patch("security_sink.notifications.smtplib.SMTP", SMTP):
            EmailSender(
                "smtp.test", 587, "monitor", "password", "from@test", ("to@test",)
            ).send("subject", "masked body")

        self.assertIn(("login", "monitor", "password"), calls)
        self.assertIn(("send", "from@test", "to@test", "masked body"), calls)


class ProvisioningTests(unittest.TestCase):
    def test_notifier_service_and_environment_are_non_containerized(self):
        service = (ROOT / "observability" / "systemd" / "security-notifier.service").read_text()
        environment = (ROOT / "security_notifier.env.example").read_text()
        self.assertIn("security_sink.notifier_worker", service)
        self.assertIn("EnvironmentFile=/etc/luck-security-notifier.env", service)
        self.assertNotIn("docker", service.lower())
        for name in (
            "SLACK_WEBHOOK_URL", "SMTP_HOST", "NOTIFICATION_MAX_RETRIES",
            "NOTIFICATION_GROUP_WINDOW_SECONDS", "NOTIFICATION_UNRESOLVED_HIGH_HOURS",
        ):
            self.assertIn(name, environment)

    def test_notifier_role_has_only_required_queue_write_access(self):
        migration = (
            ROOT.parent
            / "luck-mariadb"
            / "sql"
            / "migrate"
            / "2026-09-07_security_monitoring.sql"
        ).read_text()
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE ON security_monitoring.notification_log TO security_monitoring_notifier;",
            migration,
        )
        self.assertIn(
            "GRANT SELECT ON security_monitoring.security_event TO security_monitoring_notifier;",
            migration,
        )
        notifier_grants = "\n".join(
            line for line in migration.splitlines() if line.endswith("TO security_monitoring_notifier;")
        )
        self.assertNotIn("DELETE", notifier_grants)


if __name__ == "__main__":
    unittest.main()
