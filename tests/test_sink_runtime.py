from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from security_sink.masked_logs import TOPIC as MASKED_LOG_TOPIC
from security_sink.resilience import DLQ_TOPICS
from security_sink.runtime import kafka_config
from security_sink.security_events import TOPIC as SECURITY_EVENT_TOPIC


class SinkRuntimeTests(unittest.TestCase):
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
