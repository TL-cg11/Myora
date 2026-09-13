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


def counter(samples: list[tuple[str, dict[str, str], float]], topic: str) -> float:
    return sum(
        value
        for name, labels, value in samples
        if name == "luck_sink_messages_total" and labels.get("topic") == topic
    )


def lag_state(samples: list[tuple[str, dict[str, str], float]]) -> tuple[int, float]:
    lag = [value for name, _labels, value in samples if name == "luck_consumer_lag_messages"]
    age = [value for name, _labels, value in samples if name == "luck_consumer_oldest_message_age_seconds"]
    return int(max(lag, default=0)), max(age, default=0.0)


def histogram(samples: list[tuple[str, dict[str, str], float]], topic: str) -> dict[float, float]:
    result = {}
    for name, labels, value in samples:
        if name != "luck_sink_processing_duration_seconds_bucket" or labels.get("topic") != topic:
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


def db_end_to_end(run_id: str) -> float:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT TIMESTAMPDIFF(MICROSECOND,e.detected_at,k.processed_at)/1000000 "
                "FROM security_event e JOIN kafka_consumption k ON k.event_id=e.event_id "
                "WHERE e.event_id LIKE %s",
                (f"p13perf-{run_id}-s-%",),
            )
            samples = [max(0.0, float(row[0])) for row in cursor.fetchall()]
    finally:
        connection.close()
    return percentile_95(samples)


def db_topic_stats(run_id: str) -> dict[str, dict[str, float | int]]:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT topic_name, COUNT(*), "
                "TIMESTAMPDIFF(MICROSECOND,MIN(processed_at),MAX(processed_at))/1000000 "
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
                }
                for topic, count, window in cursor.fetchall()
            }
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
            "db_topic_stats": db_topic_stats(args.diagnose_run_id),
            "processing_p95_upper_bound_seconds": {
                SECURITY_TOPIC: histogram_p95({}, histogram(security_samples, SECURITY_TOPIC)),
                MASKED_TOPIC: histogram_p95({}, histogram(masked_samples, MASKED_TOPIC)),
            },
            "end_to_end_p95_seconds": {
                SECURITY_TOPIC: db_end_to_end(args.diagnose_run_id),
                MASKED_TOPIC: loki_end_to_end(args.loki_url, args.diagnose_run_id),
            },
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
    preflight_end = tuple(counter(metric_samples(url), topic) for url, topic in zip(urls, topics))
    preflight_by_topic = {
        topic: (value - baseline) / args.preflight_duration
        for topic, value, baseline in zip(topics, preflight_end, preflight_base)
    }
    preflight_throughput = min(preflight_by_topic.values())
    wait_for_count(urls, topics, preflight_base, preflight_count, args.drain_timeout)
    preflight_floor = args.sustained_rate * 0.8
    if preflight_throughput < preflight_floor:
        print(json.dumps({
            "status": "preflight-failed",
            "run_id": run_id,
            "messages_total": preflight_count * 2,
            "preflight_throughput": preflight_throughput,
            "preflight_throughput_by_topic": preflight_by_topic,
            "preflight_floor": preflight_floor,
            "max_lag": preflight_lag,
            "max_oldest_message_seconds": preflight_age,
        }, ensure_ascii=False, sort_keys=True))
        return 1

    sustained_initial = tuple(metric_samples(url) for url in urls)
    sustained_base = tuple(
        counter(samples, topic) for samples, topic in zip(sustained_initial, topics)
    )
    sustained_count, sustained_lag, sustained_age = produce_phase(
        producer, run_id, "sustained", args.sustained_rate, args.duration, *urls
    )
    sustained_end = tuple(counter(metric_samples(url), topic) for url, topic in zip(urls, topics))
    sustained_throughput = min(
        (value - baseline) / args.duration
        for value, baseline in zip(sustained_end, sustained_base)
    )
    wait_for_count(urls, topics, sustained_base, sustained_count, args.drain_timeout)

    burst_base_samples = tuple(metric_samples(url) for url in urls)
    burst_base = tuple(counter(samples, topic) for samples, topic in zip(burst_base_samples, topics))
    burst_count, burst_lag, burst_age = produce_phase(
        producer, run_id, "burst", args.burst_rate, args.duration, *urls
    )
    burst_end = tuple(counter(metric_samples(url), topic) for url, topic in zip(urls, topics))
    burst_throughput = min(
        (value - baseline) / args.duration for value, baseline in zip(burst_end, burst_base)
    )
    wait_for_count(urls, topics, burst_base, burst_count, args.drain_timeout)

    final = tuple(metric_samples(url) for url in urls)
    db_p95 = histogram_p95(histogram(initial[0], SECURITY_TOPIC), histogram(final[0], SECURITY_TOPIC))
    loki_p95 = histogram_p95(histogram(initial[1], MASKED_TOPIC), histogram(final[1], MASKED_TOPIC))
    end_to_end = max(db_end_to_end(run_id), loki_end_to_end(args.loki_url, run_id))
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
    print(json.dumps({"status": "ok" if result.passed else "failed", "run_id": run_id,
                      "messages_total": estimated, "snapshot": snapshot.__dict__,
                      "assessment": result.as_dict()}, ensure_ascii=False, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
