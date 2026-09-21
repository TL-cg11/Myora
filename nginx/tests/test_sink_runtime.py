from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from security_sink.masked_logs import TOPIC as MASKED_LOG_TOPIC
from security_sink.resilience import DLQ_TOPICS
from security_sink.runtime import ReusableMySQLConnectionFactory, kafka_config
from security_sink.security_events import TOPIC as SECURITY_EVENT_TOPIC


class SinkRuntimeTests(unittest.TestCase):
    def test_worker_connection_factory_reuses_and_closes_physical_connection(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.closed = 0
                self.autocommit_values: list[bool] = []

            def autocommit(self, value: bool) -> None:
                self.autocommit_values.append(value)

            def close(self) -> None:
                self.closed += 1

        physical = Connection()
        connects: list[Connection] = []

        def connect() -> Connection:
            connects.append(physical)
            return physical

        factory = ReusableMySQLConnectionFactory(connect)
        first = factory()
        first.close()
        second = factory()
        second.close()

        self.assertEqual(connects, [physical])
        self.assertIs(first._connection, second._connection)
        self.assertEqual(physical.closed, 0)
        self.assertEqual(physical.autocommit_values, [True])
        factory.close()
        self.assertEqual(physical.closed, 1)

    def test_worker_connection_factory_health_checks_and_reconnects(self) -> None:
        class Connection:
            def __init__(self, *, fails_ping: bool = False) -> None:
                self.fails_ping = fails_ping
                self.pings = 0
                self.closed = 0

            def autocommit(self, value: bool) -> None:
                self.autocommit_value = value

            def ping(self, *, reconnect: bool) -> None:
                self.pings += 1
                self.reconnect = reconnect
                if self.fails_ping:
                    raise RuntimeError("connection lost")

            def close(self) -> None:
                self.closed += 1

        first = Connection(fails_ping=True)
        second = Connection()
        connections = iter([first, second])
        now = [0.0]
        factory = ReusableMySQLConnectionFactory(
            lambda: next(connections), ping_interval=10, clock=lambda: now[0]
        )

        factory().close()
        now[0] = 11.0
        borrowed = factory()

        self.assertEqual(first.pings, 1)
        self.assertEqual(first.closed, 1)
        self.assertIs(borrowed._connection, second)
        factory.close()

    def test_native_installer_uses_remote_was_broker_and_non_root_services(self) -> None:
        root = Path(__file__).resolve().parents[1]
        example = (root / "security_sink.env.example").read_text(encoding="utf-8")
        installer = (root / "scripts/security-sink-install.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("KAFKA_BOOTSTRAP_SERVERS=100.66.77.55:9092", example)
        self.assertIn("ENV_FILE=/etc/luck-security-sink.env", installer)
        self.assertIn("EnvironmentFile=$ENV_FILE", installer)
        self.assertIn("User=$INSTALL_USER", installer)
        self.assertIn("security_sink.worker", installer)
        self.assertIn("security_sink.masked_worker", installer)
        self.assertIn("enable --now luck-security-event-sink.service", installer)

    def test_topics_match_detector_outputs_and_sink_dlqs(self) -> None:
        self.assertEqual(SECURITY_EVENT_TOPIC, "myohan.security-events")
        self.assertEqual(MASKED_LOG_TOPIC, "myohan.masked-logs")
        self.assertEqual(
            DLQ_TOPICS,
            {
                "myohan.security-events": "myohan.security-events.sink-dlq",
                "myohan.masked-logs": "myohan.masked-logs.sink-dlq",
            },
        )

    def test_workers_use_distinct_groups_and_disable_auto_commit(self) -> None:
        environment = {"KAFKA_BOOTSTRAP_SERVERS": "broker.test:9092"}
        with patch.dict(os.environ, environment, clear=True):
            security = kafka_config(
                "security-event-sink", "SECURITY_EVENT_CONSUMER_GROUP"
            )
            masked = kafka_config("masked-log-sink", "MASKED_LOG_CONSUMER_GROUP")

        self.assertEqual(security["group.id"], "security-event-sink")
        self.assertEqual(masked["group.id"], "masked-log-sink")
        self.assertFalse(security["enable.auto.commit"])
        self.assertFalse(masked["enable.auto.commit"])

    def test_group_environment_overrides_only_its_worker(self) -> None:
        environment = {
            "KAFKA_BOOTSTRAP_SERVERS": "broker.test:9092",
            "MASKED_LOG_CONSUMER_GROUP": "masked-log-sink-blue",
        }
        with patch.dict(os.environ, environment, clear=True):
            security = kafka_config(
                "security-event-sink", "SECURITY_EVENT_CONSUMER_GROUP"
            )
            masked = kafka_config("masked-log-sink", "MASKED_LOG_CONSUMER_GROUP")

        self.assertEqual(security["group.id"], "security-event-sink")
        self.assertEqual(masked["group.id"], "masked-log-sink-blue")


if __name__ == "__main__":
    unittest.main()
