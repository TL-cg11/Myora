from __future__ import annotations

import unittest
import json
from pathlib import Path
from urllib.request import urlopen

from security_sink.common import payload_age_seconds
from security_sink.metrics import DLQ_STAGES, MetricsServer, SinkMetrics, observe_kafka_position
from security_sink.metrics_verification import REQUIRED_METRICS, verify_metrics_runtime
from security_sink.retention import RETENTION_QUERIES, RetentionVerification


class FakeMessage:
    def topic(self): return "myohan.security-events"
    def partition(self): return 2
    def offset(self): return 90
    def timestamp(self): return (1, 1_788_799_999_000)


class FakeConsumer:
    def get_watermark_offsets(self, _partition, cached=False):
        self.cached = cached
        return (0, 100)


class SinkMetricsTests(unittest.TestCase):
    def test_dlq_counters_are_exposed_at_zero_before_the_first_failure(self) -> None:
        metrics = SinkMetrics("masked-log-sink")
        metrics.initialize_dlq("myohan.masked-logs")

        rendered = metrics.render().decode()

        for stage in DLQ_STAGES:
            self.assertIn(
                'luck_sink_dlq_total{consumer_group="masked-log-sink",'
                f'topic="myohan.masked-logs",stage="{stage}"}} 0',
                rendered,
            )

    def test_render_contains_result_failure_retry_dlq_latency_and_lag(self) -> None:
        metrics = SinkMetrics("security-event-sink")
        metrics.record_message("myohan.security-events", "processed", 0.2, 0.4)
        metrics.record_commit("myohan.security-events", 0.03)
        metrics.record_failure("myohan.security-events", "database")
        metrics.record_retry("myohan.security-events", "database")
        metrics.record_dlq("myohan.security-events", "schema_validation")
        metrics.set_partition_lag("myohan.security-events", 2, 9, 1.5)

        rendered = metrics.render().decode()

        for name in (
            "luck_sink_messages_total",
            "luck_sink_failures_total",
            "luck_sink_retries_total",
            "luck_sink_dlq_total",
            "luck_sink_processing_duration_seconds_bucket",
            "luck_sink_commit_duration_seconds_bucket",
            "luck_sink_end_to_end_duration_seconds_bucket",
            "luck_consumer_lag_messages",
            "luck_consumer_oldest_message_age_seconds",
        ):
            self.assertIn(name, rendered)
        self.assertIn('consumer_group="security-event-sink"', rendered)
        self.assertIn('partition="2"} 9', rendered)

    def test_payload_age_uses_source_utc_timestamp_and_invalid_input_is_ignored(self) -> None:
        from datetime import datetime, timezone

        now = datetime(2026, 9, 13, 0, 0, 10, tzinfo=timezone.utc)
        self.assertEqual(
            payload_age_seconds(b'{"occurred_at":"2026-09-13T00:00:08.000Z"}', now=now),
            2.0,
        )
        self.assertIsNone(payload_age_seconds(b"invalid", now=now))

    def test_metrics_http_server_exposes_only_metrics(self) -> None:
        metrics = SinkMetrics("masked-log-sink")
        metrics.record_message("myohan.masked-logs", "processed", 0.01)
        server = MetricsServer(metrics, "127.0.0.1", 0)
        server.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.port}/metrics") as response:
                body = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertIn("luck_sink_messages_total", body)
        finally:
            server.close()

    def test_kafka_watermark_updates_partition_lag(self) -> None:
        metrics = SinkMetrics("security-event-sink")
        consumer = FakeConsumer()
        observe_kafka_position(
            metrics,
            consumer,
            FakeMessage(),
            lambda topic, partition: (topic, partition),
        )
        rendered = metrics.render().decode()
        self.assertIn('partition="2"} 9', rendered)
        self.assertFalse(consumer.cached)

    def test_zero_lag_resets_oldest_message_age(self) -> None:
        class CaughtUpConsumer:
            def get_watermark_offsets(self, _partition, cached=False):
                return (0, 91)

        metrics = SinkMetrics("security-event-sink")
        observe_kafka_position(
            metrics, CaughtUpConsumer(), FakeMessage(),
            lambda topic, partition: (topic, partition),
        )
        rendered = metrics.render().decode()
        self.assertIn('luck_consumer_oldest_message_age_seconds{consumer_group="security-event-sink",topic="myohan.security-events",partition="2"} 0', rendered)


class RetentionPolicyTests(unittest.TestCase):
    def test_all_required_retention_windows_are_defined(self) -> None:
        self.assertEqual(
            set(RETENTION_QUERIES),
            {
                "security_event_365d",
                "kafka_consumption_14d",
                "consumer_failure_90d",
                "notification_log_90d",
            },
        )
        self.assertIn("INTERVAL 14 DAY", RETENTION_QUERIES["kafka_consumption_14d"])
        self.assertIn("INTERVAL 90 DAY", RETENTION_QUERIES["consumer_failure_90d"])

    def test_retention_passes_only_when_no_overdue_rows_remain(self) -> None:
        self.assertTrue(RetentionVerification({"a": 0, "b": 0}).passed)
        self.assertFalse(RetentionVerification({"a": 0, "b": 1}).passed)


class MetricsRuntimeVerificationTests(unittest.TestCase):
    def fetch(self, url: str, _timeout: float) -> str:
        if url.endswith("/metrics"):
            return "\n".join(f"# HELP {name} test" for name in REQUIRED_METRICS)
        if url.endswith("/api/v1/status/flags"):
            return json.dumps(
                {"status": "success", "data": {"storage.tsdb.retention.time": "30d"}}
            )
        if "/api/v1/query?" in url:
            return json.dumps(
                {
                    "status": "success",
                    "data": {
                        "result": [
                            {"value": [1, "1"]},
                            {"value": [1, "1"]},
                        ]
                    },
                }
            )
        raise AssertionError(url)

    def test_two_sink_targets_and_prometheus_retention_pass(self) -> None:
        result = verify_metrics_runtime(
            "http://127.0.0.1:9090",
            ["http://was:9108", "http://was:9109"],
            fetch=self.fetch,
        )
        self.assertEqual(result.targets, 2)
        self.assertEqual(result.prometheus_retention, "30d")

    def test_missing_metric_or_scrape_target_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required metrics"):
            verify_metrics_runtime(
                "http://127.0.0.1:9090",
                ["http://was:9108"],
                fetch=lambda _url, _timeout: "",
            )

    def test_prometheus_file_discovery_and_30_day_retention_are_configured(self) -> None:
        root = Path(__file__).resolve().parents[1]
        prometheus = (root / "observability/prometheus/prometheus.yml").read_text()
        targets = (root / "observability/prometheus/kafka-consumer-targets.yml").read_text()
        service = (root / "observability/systemd/prometheus.service").read_text()
        self.assertIn("file_sd_configs", prometheus)
        self.assertIn("100.117.253.9:9108", targets)
        self.assertIn("100.117.253.9:9109", targets)
        self.assertIn("--storage.tsdb.retention.time=30d", service)


if __name__ == "__main__":
    unittest.main()
