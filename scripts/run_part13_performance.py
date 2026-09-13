#!/usr/bin/env python3
"""Run the Part 13-11 Kafka sink throughput, lag, and latency test."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.performance import PerformanceSnapshot, assess, percentile_95  # noqa: E402
from security_sink.runtime import kafka_config, kafka_producer_config, mysql_connection  # noqa: E402


SECURITY_TOPIC = "myohan.security-events"
MASKED_TOPIC = "myohan.masked-logs"
LABEL_RE = re.compile(r'(\w+)="((?:\\.|[^"])*)"')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def security_record(event_id: str, occurred_at: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "source_event_id": event_id.replace("-s-", "-raw-"),
        "schema_version": "1.0",
        "request_id": event_id,
        "occurred_at": occurred_at,
        "detected_at": occurred_at,
        "environment": "test",
        "source_service": "part13-performance",
        "source_type": "synthetic",
        "event_name": "retention.performance.test",
        "risk_level": "LOW",
        "risk_score": 1,
        "detector_version": "part13-test",
        "masking_policy_version": "part13-test",
        "masked_excerpt": "part13 performance fixture",
        "body_hash": hashlib.sha256(event_id.encode()).hexdigest(),
        "safe_metadata": {"fixture": "part13-performance"},
        "detections": [
            {
                "detection_id": event_id.replace("-s-", "-d-"),
                "rule_id": "PART13_PERFORMANCE",
                "rule_version": "1",
                "category": "BEHAVIOR",
                "entity_type": "performance_fixture",
                "risk_level": "LOW",
                "confidence": 1.0,
                "match_count": 1,
                "evidence_fingerprint": None,
                "locations_json": None,
            }
        ],
    }


def masked_record(event_id: str, occurred_at: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "schema_version": "1.0",
        "request_id": event_id,
        "occurred_at": occurred_at,
        "environment": "test",
        "source_service": "part13-performance",
        "source_type": "synthetic",
        "masking_policy_version": "part13-test",
        "masked_message": "part13 performance masked fixture",
        "body_hash": hashlib.sha256(event_id.encode()).hexdigest(),
        "safe_metadata": {"fixture": "part13-performance"},
    }


def fetch_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def metric_samples(url: str) -> list[tuple[str, dict[str, str], float]]:
    samples = []
    for line in fetch_text(url).splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name_and_labels, raw_value = line.rsplit(" ", 1)
        name = name_and_labels.split("{", 1)[0]
        labels = {
            key: value.replace('\\"', '"').replace("\\\\", "\\")
            for key, value in LABEL_RE.findall(name_and_labels)
        }
        try:
            samples.append((name, labels, float(raw_value)))
        except ValueError:
            continue
    return samples


def counter(
    samples: list[tuple[str, dict[str, str], float]],
    topic: str,
    result: str | None = None,
) -> float:
    return sum(
        value
        for name, labels, value in samples
        if name == "luck_sink_messages_total"
        and labels.get("topic") == topic
        and (result is None or labels.get("result") == result)
    )


def result_counts(
    before: list[tuple[str, dict[str, str], float]],
    after: list[tuple[str, dict[str, str], float]],
    topic: str,
) -> dict[str, int]:
    results = {
        labels["result"]
        for name, labels, _value in before + after
        if name == "luck_sink_messages_total"
        and labels.get("topic") == topic
        and "result" in labels
    }
    return {
        result: int(max(0.0, counter(after, topic, result) - counter(before, topic, result)))
        for result in sorted(results)
    }


def lag_state(samples: list[tuple[str, dict[str, str], float]]) -> tuple[int, float]:
    lag = [value for name, _labels, value in samples if name == "luck_consumer_lag_messages"]
    age = [value for name, _labels, value in samples if name == "luck_consumer_oldest_message_age_seconds"]
    return int(max(lag, default=0)), max(age, default=0.0)


def histogram(
    samples: list[tuple[str, dict[str, str], float]],
    topic: str,
    metric_name: str = "luck_sink_processing_duration_seconds_bucket",
) -> dict[float, float]:
    result = {}
    for name, labels, value in samples:
        if name != metric_name or labels.get("topic") != topic:
            continue
        bound = math.inf if labels.get("le") == "+Inf" else float(labels["le"])
        result[bound] = value
    return result


def histogram_p95(before: dict[float, float], after: dict[float, float]) -> float:
    deltas = {bound: max(0.0, value - before.get(bound, 0.0)) for bound, value in after.items()}
    total = deltas.get(math.inf, 0.0)
    if total <= 0:
        raise RuntimeError("no processing latency samples were recorded")
    threshold = total * 0.95
    for bound in sorted(deltas):
        if deltas[bound] >= threshold:
            return bound
    return math.inf


def histogram_p95_or_none(
    before: dict[float, float], after: dict[float, float]
) -> float | None:
    try:
        return histogram_p95(before, after)
    except RuntimeError:
        return None


def histogram_average(
    before: list[tuple[str, dict[str, str], float]],
    after: list[tuple[str, dict[str, str], float]],
    topic: str,
    metric_name: str,
) -> float | None:
    def value(samples: list[tuple[str, dict[str, str], float]], suffix: str) -> float:
        return sum(
            sample
            for name, labels, sample in samples
            if name == f"{metric_name}_{suffix}" and labels.get("topic") == topic
        )

    count = max(0.0, value(after, "count") - value(before, "count"))
    total = max(0.0, value(after, "sum") - value(before, "sum"))
    return total / count if count else None


def latency_averages(
    before_samples: tuple[list[tuple[str, dict[str, str], float]], ...],
    after_samples: tuple[list[tuple[str, dict[str, str], float]], ...],
    topics: tuple[str, str],
) -> dict[str, dict[str, float | None]]:
    metrics = {
        "processing": "luck_sink_processing_duration_seconds",
        "commit": "luck_sink_commit_duration_seconds",
        "end_to_end": "luck_sink_end_to_end_duration_seconds",
    }
    return {
        topic: {
            label: histogram_average(before, after, topic, metric)
            for label, metric in metrics.items()
        }
        for topic, before, after in zip(topics, before_samples, after_samples)
    }


def produce_phase(producer: Any, run_id: str, phase: str, rate: int, duration: int,
                  security_url: str, masked_url: str) -> tuple[int, int, float]:
    total = rate * duration
    started = time.monotonic()
    next_sample = started
    max_lag = 0
    max_age = 0.0
    for sequence in range(total):
        target = started + sequence / rate
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        occurred_at = utc_now()
        security_id = f"p13perf-{run_id}-s-{phase[0]}{sequence:05d}"
        masked_id = f"p13perf-{run_id}-m-{phase[0]}{sequence:05d}"
        producer.produce(SECURITY_TOPIC, key=security_id, value=json.dumps(security_record(security_id, occurred_at)))
        producer.produce(MASKED_TOPIC, key=masked_id, value=json.dumps(masked_record(masked_id, occurred_at)))
        producer.poll(0)
        if time.monotonic() >= next_sample:
            for url in (security_url, masked_url):
                lag, age = lag_state(metric_samples(url))
                max_lag, max_age = max(max_lag, lag), max(max_age, age)
            next_sample = time.monotonic() + 1
    remaining = producer.flush(30)
    if remaining:
        raise RuntimeError(f"Kafka producer flush left {remaining} messages")
    elapsed = time.monotonic() - started
    return total, max_lag, max_age


def wait_for_count(urls: tuple[str, str], topics: tuple[str, str], baselines: tuple[float, float],
                   expected: int, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        values = tuple(counter(metric_samples(url), topic) for url, topic in zip(urls, topics))
        if all(value - baseline >= expected for value, baseline in zip(values, baselines)):
            return
        time.sleep(2)
    raise TimeoutError(f"consumers did not process {expected} messages within {timeout}s")


def db_end_to_end(run_id: str) -> float | None:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT TIMESTAMPDIFF(MICROSECOND,detected_at,created_at)/1000000 "
                "FROM security_event WHERE event_id LIKE %s",
                (f"p13perf-{run_id}-s-%",),
            )
            samples = [max(0.0, float(row[0])) for row in cursor.fetchall()]
    finally:
        connection.close()
    return percentile_95(samples) if samples else None


def db_event_count(run_id: str) -> int:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM security_event WHERE event_id LIKE %s",
                (f"p13perf-{run_id}-s-%",),
            )
            return int(cursor.fetchone()[0])
    finally:
        connection.close()


def db_topic_stats(run_id: str) -> dict[str, dict[str, float | int]]:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT topic_name, COUNT(*), "
                "TIMESTAMPDIFF(MICROSECOND,MIN(processed_at),MAX(processed_at))/1000000 "
                ", SUM(processing_status='PROCESSED'), SUM(processing_status='DLQ'), "
                "SUM(processing_status='FAILED') "
                "FROM kafka_consumption WHERE event_id LIKE %s GROUP BY topic_name",
                (f"p13perf-{run_id}-%",),
            )
            return {
                str(topic): {
                    "count": int(count),
                    "processing_window_seconds": float(window or 0),
                    "drain_throughput": (
                        int(count) / float(window) if float(window or 0) > 0 else 0.0
                    ),
                    "processed": int(processed),
                    "dlq": int(dlq),
                    "failed": int(failed),
                }
                for topic, count, window, processed, dlq, failed in cursor.fetchall()
            }
    finally:
        connection.close()


def db_phase_throughput(
    run_id: str, phase: str, offered_rate: int
) -> dict[str, float]:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT topic_name, COUNT(*), "
                "TIMESTAMPDIFF(MICROSECOND,MIN(processed_at),MAX(processed_at))/1000000 "
                "FROM kafka_consumption WHERE event_id LIKE %s "
                "AND processing_status='PROCESSED' GROUP BY topic_name",
                (f"p13perf-{run_id}-%-{phase[0]}%",),
            )
            result = {}
            for topic, count, window in cursor.fetchall():
                elapsed = float(window or 0)
                measured = int(count) / elapsed if elapsed > 0 else 0.0
                result[str(topic)] = min(float(offered_rate), measured)
            return result
    finally:
        connection.close()


def loki_end_to_end(base_url: str, run_id: str) -> float:
    end_ns = time.time_ns()
    query = urlencode({
        "query": '{pipeline="security-masked-logs",data_class="masked"} |= "p13perf-' + run_id + '"',
        "start": end_ns - 3_600_000_000_000,
        "end": end_ns,
        "limit": 5000,
        "direction": "backward",
    })
    payload = json.loads(fetch_text(base_url.rstrip("/") + "/loki/api/v1/query_range?" + query))
    samples = []
    for stream in payload.get("data", {}).get("result", []):
        for timestamp, line in stream.get("values", []):
            record = json.loads(line)
            occurred = datetime.fromisoformat(record["occurred_at"].replace("Z", "+00:00")).timestamp()
            samples.append(max(0.0, int(timestamp) / 1_000_000_000 - occurred))
    return percentile_95(samples)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--diagnose-run-id")
    parser.add_argument("--preflight-duration", type=int, default=5)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--sustained-rate", type=int, default=100)
    parser.add_argument("--burst-rate", type=int, default=300)
    parser.add_argument("--drain-timeout", type=int, default=600)
    parser.add_argument("--security-metrics-url", default="http://100.117.253.9:9108/metrics")
    parser.add_argument("--masked-metrics-url", default="http://100.117.253.9:9109/metrics")
    parser.add_argument("--loki-url", default="http://127.0.0.1:3100")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if min(
        args.preflight_duration,
        args.duration,
        args.sustained_rate,
        args.burst_rate,
        args.drain_timeout,
    ) <= 0:
        raise ValueError("durations, rates, and drain timeout must be positive")
    if args.diagnose_run_id:
        if re.fullmatch(r"[0-9a-f]{12}", args.diagnose_run_id) is None:
            raise ValueError("diagnose run id must be 12 lowercase hexadecimal characters")
        security_samples = metric_samples(args.security_metrics_url)
        masked_samples = metric_samples(args.masked_metrics_url)
        security_lag, security_age = lag_state(security_samples)
        masked_lag, masked_age = lag_state(masked_samples)
        report = {
            "status": "diagnostic",
            "run_id": args.diagnose_run_id,
            "security_event_count": db_event_count(args.diagnose_run_id),
            "db_topic_stats": db_topic_stats(args.diagnose_run_id),
            "processing_p95_upper_bound_seconds": {
                SECURITY_TOPIC: histogram_p95_or_none({}, histogram(security_samples, SECURITY_TOPIC)),
                MASKED_TOPIC: histogram_p95_or_none({}, histogram(masked_samples, MASKED_TOPIC)),
            },
            "commit_p95_upper_bound_seconds": {
                SECURITY_TOPIC: histogram_p95_or_none(
                    {}, histogram(security_samples, SECURITY_TOPIC,
                                  "luck_sink_commit_duration_seconds_bucket")
                ),
                MASKED_TOPIC: histogram_p95_or_none(
                    {}, histogram(masked_samples, MASKED_TOPIC,
                                  "luck_sink_commit_duration_seconds_bucket")
                ),
            },
            "measured_end_to_end_p95_upper_bound_seconds": {
                SECURITY_TOPIC: histogram_p95_or_none(
                    {}, histogram(security_samples, SECURITY_TOPIC,
                                  "luck_sink_end_to_end_duration_seconds_bucket")
                ),
                MASKED_TOPIC: histogram_p95_or_none(
                    {}, histogram(masked_samples, MASKED_TOPIC,
                                  "luck_sink_end_to_end_duration_seconds_bucket")
                ),
            },
            "end_to_end_p95_seconds": {
                SECURITY_TOPIC: db_end_to_end(args.diagnose_run_id),
                MASKED_TOPIC: None,
            },
            "masked_end_to_end_note": (
                "unavailable from stored logs because Loki preserves the source occurred_at timestamp"
            ),
            "current_lag": {SECURITY_TOPIC: security_lag, MASKED_TOPIC: masked_lag},
            "current_oldest_message_seconds": {
                SECURITY_TOPIC: security_age,
                MASKED_TOPIC: masked_age,
            },
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0

    estimated = 2 * (
        args.preflight_duration * args.sustained_rate
        + args.duration * (args.sustained_rate + args.burst_rate)
    )
    if not args.execute:
        print(json.dumps({"status": "dry-run", "messages_total": estimated,
                          "duration_seconds": args.preflight_duration + args.duration * 2,
                          "requires_execute": True}, sort_keys=True))
        return 0

    urls = (args.security_metrics_url, args.masked_metrics_url)
    topics = (SECURITY_TOPIC, MASKED_TOPIC)
    run_id = uuid.uuid4().hex[:12]
    initial = tuple(metric_samples(url) for url in urls)
    if any(lag_state(samples)[0] != 0 for samples in initial):
        raise RuntimeError("consumer lag must be zero before the performance test")
    producer = __import__("confluent_kafka").Producer(
        kafka_producer_config(kafka_config("part13-performance", "PART13_PERFORMANCE_GROUP"))
    )

    preflight_base = tuple(counter(samples, topic) for samples, topic in zip(initial, topics))
    preflight_count, preflight_lag, preflight_age = produce_phase(
        producer, run_id, "preflight", args.sustained_rate,
        args.preflight_duration, *urls
    )
    wait_for_count(urls, topics, preflight_base, preflight_count, args.drain_timeout)
    preflight_final = tuple(metric_samples(url) for url in urls)
    measured_preflight = db_phase_throughput(
        run_id, "preflight", args.sustained_rate
    )
    preflight_by_topic = {
        topic: measured_preflight.get(topic, 0.0) for topic in topics
    }
    preflight_throughput = min(preflight_by_topic.values())
    preflight_floor = args.sustained_rate * 0.8
    if preflight_throughput < preflight_floor:
        print(json.dumps({
            "status": "preflight-failed",
            "run_id": run_id,
            "messages_total": preflight_count * 2,
            "preflight_throughput": preflight_throughput,
            "preflight_throughput_by_topic": preflight_by_topic,
            "preflight_floor": preflight_floor,
            "terminal_results_by_topic": {
                topic: result_counts(before, after, topic)
                for topic, before, after in zip(topics, initial, preflight_final)
            },
            "average_seconds_by_topic": latency_averages(
                initial, preflight_final, topics
            ),
            "max_lag": preflight_lag,
            "max_oldest_message_seconds": preflight_age,
            "processing_p95_upper_bound_seconds": {
                topic: histogram_p95(
                    histogram(before, topic), histogram(after, topic)
                )
                for topic, before, after in zip(topics, initial, preflight_final)
            },
            "commit_p95_upper_bound_seconds": {
                topic: histogram_p95(
                    histogram(before, topic, "luck_sink_commit_duration_seconds_bucket"),
                    histogram(after, topic, "luck_sink_commit_duration_seconds_bucket"),
                )
                for topic, before, after in zip(topics, initial, preflight_final)
            },
            "end_to_end_p95_upper_bound_seconds": {
                topic: histogram_p95(
                    histogram(before, topic, "luck_sink_end_to_end_duration_seconds_bucket"),
                    histogram(after, topic, "luck_sink_end_to_end_duration_seconds_bucket"),
                )
                for topic, before, after in zip(topics, initial, preflight_final)
            },
        }, ensure_ascii=False, sort_keys=True))
        return 1

    sustained_initial = tuple(metric_samples(url) for url in urls)
    sustained_base = tuple(
        counter(samples, topic) for samples, topic in zip(sustained_initial, topics)
    )
    sustained_count, sustained_lag, sustained_age = produce_phase(
        producer, run_id, "sustained", args.sustained_rate, args.duration, *urls
    )
    wait_for_count(urls, topics, sustained_base, sustained_count, args.drain_timeout)
    sustained_by_topic = db_phase_throughput(
        run_id, "sustained", args.sustained_rate
    )
    sustained_throughput = min(
        sustained_by_topic.get(topic, 0.0) for topic in topics
    )

    burst_base_samples = tuple(metric_samples(url) for url in urls)
    burst_base = tuple(counter(samples, topic) for samples, topic in zip(burst_base_samples, topics))
    burst_count, burst_lag, burst_age = produce_phase(
        producer, run_id, "burst", args.burst_rate, args.duration, *urls
    )
    wait_for_count(urls, topics, burst_base, burst_count, args.drain_timeout)
    burst_by_topic = db_phase_throughput(run_id, "burst", args.burst_rate)
    burst_throughput = min(burst_by_topic.get(topic, 0.0) for topic in topics)

    final = tuple(metric_samples(url) for url in urls)
    db_p95 = histogram_p95(histogram(initial[0], SECURITY_TOPIC), histogram(final[0], SECURITY_TOPIC))
    loki_p95 = histogram_p95(histogram(initial[1], MASKED_TOPIC), histogram(final[1], MASKED_TOPIC))
    end_to_end = max(
        histogram_p95(
            histogram(before, topic, "luck_sink_end_to_end_duration_seconds_bucket"),
            histogram(after, topic, "luck_sink_end_to_end_duration_seconds_bucket"),
        )
        for topic, before, after in zip(topics, initial, final)
    )
    snapshot = PerformanceSnapshot(
        sustained_throughput=sustained_throughput,
        burst_throughput=burst_throughput,
        db_p95_seconds=db_p95,
        loki_p95_seconds=loki_p95,
        end_to_end_p95_seconds=end_to_end,
        consumer_lag=max(preflight_lag, sustained_lag, burst_lag),
        oldest_message_seconds=max(preflight_age, sustained_age, burst_age),
    )
    result = assess(snapshot)
    terminal_results = {
        topic: result_counts(before, after, topic)
        for topic, before, after in zip(topics, initial, final)
    }
    terminal_results_ok = all(
        counts.get("processed", 0) == estimated // 2
        and sum(value for name, value in counts.items() if name != "processed") == 0
        for counts in terminal_results.values()
    )
    passed = result.passed and terminal_results_ok
    print(json.dumps({"status": "ok" if passed else "failed", "run_id": run_id,
                      "messages_total": estimated, "snapshot": snapshot.__dict__,
                      "throughput_by_topic": {
                          "sustained": sustained_by_topic,
                          "burst": burst_by_topic,
                      },
                      "terminal_results_by_topic": terminal_results,
                      "terminal_results_ok": terminal_results_ok,
                      "average_seconds_by_topic": latency_averages(
                          initial, final, topics
                      ),
                      "assessment": result.as_dict()}, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
        }, ensure_ascii=False, sort_keys=True))
        raise SystemExit(2)
