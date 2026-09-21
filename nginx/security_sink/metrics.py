"""Dependency-free Prometheus metrics for security sink consumers."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
DLQ_STAGES = ("schema_validation", "masking_validation", "sink_processing")


def _labels(values: tuple[tuple[str, str], ...]) -> str:
    rendered = []
    for name, value in values:
        safe = value.replace("\\", "\\\\").replace('"', '\\"')
        rendered.append(f'{name}="{safe}"')
    return "{" + ",".join(rendered) + "}" if rendered else ""


class SinkMetrics:
    def __init__(self, consumer_group: str) -> None:
        self.consumer_group = consumer_group
        self._lock = threading.Lock()
        self._messages: dict[tuple[str, str], float] = defaultdict(float)
        self._failures: dict[tuple[str, str], float] = defaultdict(float)
        self._retries: dict[tuple[str, str], float] = defaultdict(float)
        self._dlq: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_buckets: dict[str, list[int]] = {}
        self._duration_sum: dict[str, float] = defaultdict(float)
        self._duration_count: dict[str, int] = defaultdict(int)
        self._commit_buckets: dict[str, list[int]] = {}
        self._commit_sum: dict[str, float] = defaultdict(float)
        self._commit_count: dict[str, int] = defaultdict(int)
        self._end_to_end_buckets: dict[str, list[int]] = {}
        self._end_to_end_sum: dict[str, float] = defaultdict(float)
        self._end_to_end_count: dict[str, int] = defaultdict(int)
        self._lag: dict[tuple[str, int], float] = {}
        self._age: dict[tuple[str, int], float] = {}

    def initialize_dlq(self, topic: str) -> None:
        """Expose zero-valued DLQ counters before the first failure occurs."""
        with self._lock:
            for stage in DLQ_STAGES:
                self._dlq.setdefault((topic, stage), 0.0)

    def record_message(
        self, topic: str, result: str, duration: float,
        end_to_end_duration: float | None = None,
    ) -> None:
        with self._lock:
            self._messages[(topic, result)] += 1
            duration = max(0.0, duration)
            counts = self._duration_buckets.setdefault(topic, [0] * len(BUCKETS))
            for index, bucket in enumerate(BUCKETS):
                if duration <= bucket:
                    counts[index] += 1
            self._duration_sum[topic] += duration
            self._duration_count[topic] += 1
            if end_to_end_duration is not None:
                end_to_end_duration = max(0.0, end_to_end_duration)
                end_counts = self._end_to_end_buckets.setdefault(topic, [0] * len(BUCKETS))
                for index, bucket in enumerate(BUCKETS):
                    if end_to_end_duration <= bucket:
                        end_counts[index] += 1
                self._end_to_end_sum[topic] += end_to_end_duration
                self._end_to_end_count[topic] += 1

    def record_failure(self, topic: str, stage: str) -> None:
        with self._lock:
            self._failures[(topic, stage)] += 1

    def record_commit(self, topic: str, duration: float) -> None:
        with self._lock:
            duration = max(0.0, duration)
            counts = self._commit_buckets.setdefault(topic, [0] * len(BUCKETS))
            for index, bucket in enumerate(BUCKETS):
                if duration <= bucket:
                    counts[index] += 1
            self._commit_sum[topic] += duration
            self._commit_count[topic] += 1

    def record_retry(self, topic: str, stage: str) -> None:
        with self._lock:
            self._retries[(topic, stage)] += 1

    def record_dlq(self, topic: str, stage: str) -> None:
        with self._lock:
            self._dlq[(topic, stage)] += 1

    def set_partition_lag(
        self, topic: str, partition: int, lag: int, oldest_age_seconds: float
    ) -> None:
        with self._lock:
            key = (topic, partition)
            self._lag[key] = max(0, lag)
            self._age[key] = max(0.0, oldest_age_seconds)

    def render(self) -> bytes:
        with self._lock:
            messages, failures = dict(self._messages), dict(self._failures)
            retries, dlq = dict(self._retries), dict(self._dlq)
            duration_buckets = {
                key: list(value) for key, value in self._duration_buckets.items()
            }
            duration_sum = dict(self._duration_sum)
            duration_count = dict(self._duration_count)
            commit_buckets = {key: list(value) for key, value in self._commit_buckets.items()}
            commit_sum = dict(self._commit_sum)
            commit_count = dict(self._commit_count)
            end_to_end_buckets = {key: list(value) for key, value in self._end_to_end_buckets.items()}
            end_to_end_sum = dict(self._end_to_end_sum)
            end_to_end_count = dict(self._end_to_end_count)
            lag, age = dict(self._lag), dict(self._age)
        lines = ["# HELP luck_sink_messages_total Sink messages by terminal result.", "# TYPE luck_sink_messages_total counter"]
        for (topic, result), value in sorted(messages.items()):
            labels = (("consumer_group", self.consumer_group), ("topic", topic), ("result", result))
            lines.append(f"luck_sink_messages_total{_labels(labels)} {value:g}")
        for name, help_text, values in (
            ("luck_sink_failures_total", "Sink failures by stage.", failures),
            ("luck_sink_retries_total", "Sink retries by stage.", retries),
            ("luck_sink_dlq_total", "Messages sent to DLQ by stage.", dlq),
        ):
            lines += [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
            for (topic, stage), value in sorted(values.items()):
                labels = (("consumer_group", self.consumer_group), ("topic", topic), ("stage", stage))
                lines.append(f"{name}{_labels(labels)} {value:g}")
        lines += ["# HELP luck_sink_processing_duration_seconds Sink processing latency.", "# TYPE luck_sink_processing_duration_seconds histogram"]
        for topic, counts in sorted(duration_buckets.items()):
            base = (("consumer_group", self.consumer_group), ("topic", topic))
            for bucket, count in zip(BUCKETS, counts):
                labels = base + (("le", str(bucket)),)
                lines.append(f"luck_sink_processing_duration_seconds_bucket{_labels(labels)} {count}")
            infinite_labels = base + (("le", "+Inf"),)
            lines.append(f"luck_sink_processing_duration_seconds_bucket{_labels(infinite_labels)} {duration_count[topic]}")
            lines.append(f"luck_sink_processing_duration_seconds_sum{_labels(base)} {duration_sum[topic]:g}")
            lines.append(f"luck_sink_processing_duration_seconds_count{_labels(base)} {duration_count[topic]}")
        lines += ["# HELP luck_sink_commit_duration_seconds Synchronous Kafka offset commit latency.", "# TYPE luck_sink_commit_duration_seconds histogram"]
        for topic, counts in sorted(commit_buckets.items()):
            base = (("consumer_group", self.consumer_group), ("topic", topic))
            for bucket, count in zip(BUCKETS, counts):
                bucket_labels = base + (("le", str(bucket)),)
                lines.append(f"luck_sink_commit_duration_seconds_bucket{_labels(bucket_labels)} {count}")
            infinite_labels = base + (("le", "+Inf"),)
            lines.append(f"luck_sink_commit_duration_seconds_bucket{_labels(infinite_labels)} {commit_count[topic]}")
            lines.append(f"luck_sink_commit_duration_seconds_sum{_labels(base)} {commit_sum[topic]:g}")
            lines.append(f"luck_sink_commit_duration_seconds_count{_labels(base)} {commit_count[topic]}")
        lines += ["# HELP luck_sink_end_to_end_duration_seconds Source occurrence to sink completion latency.", "# TYPE luck_sink_end_to_end_duration_seconds histogram"]
        for topic, counts in sorted(end_to_end_buckets.items()):
            base = (("consumer_group", self.consumer_group), ("topic", topic))
            for bucket, count in zip(BUCKETS, counts):
                bucket_labels = base + (("le", str(bucket)),)
                lines.append(f"luck_sink_end_to_end_duration_seconds_bucket{_labels(bucket_labels)} {count}")
            infinite_labels = base + (("le", "+Inf"),)
            lines.append(f"luck_sink_end_to_end_duration_seconds_bucket{_labels(infinite_labels)} {end_to_end_count[topic]}")
            lines.append(f"luck_sink_end_to_end_duration_seconds_sum{_labels(base)} {end_to_end_sum[topic]:g}")
            lines.append(f"luck_sink_end_to_end_duration_seconds_count{_labels(base)} {end_to_end_count[topic]}")
        for name, help_text, values in (
            ("luck_consumer_lag_messages", "Kafka consumer lag by partition.", lag),
            ("luck_consumer_oldest_message_age_seconds", "Age of last processed Kafka message.", age),
        ):
            lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
            for (topic, partition), value in sorted(values.items()):
                labels = (("consumer_group", self.consumer_group), ("topic", topic), ("partition", str(partition)))
                lines.append(f"{name}{_labels(labels)} {value:g}")
        return ("\n".join(lines) + "\n").encode()


class MetricsServer:
    def __init__(self, metrics: SinkMetrics, host: str, port: int) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/metrics":
                    self.send_error(404)
                    return
                body = metrics.render()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *args: Any) -> None:
                return None

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def observe_kafka_position(
    metrics: SinkMetrics,
    consumer: Any,
    message: Any,
    topic_partition_factory: Any,
) -> None:
    topic, partition = message.topic(), message.partition()
    _low, high = consumer.get_watermark_offsets(
        topic_partition_factory(topic, partition), cached=False
    )
    _timestamp_type, timestamp_ms = message.timestamp()
    age = max(0.0, time.time() - timestamp_ms / 1000) if timestamp_ms > 0 else 0.0
    lag = max(0, high - message.offset() - 1)
    metrics.set_partition_lag(topic, partition, lag, age if lag else 0.0)
