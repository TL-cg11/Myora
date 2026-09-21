#!/usr/bin/env python3
"""Run the ``myohan.security-events`` Kafka-to-MariaDB worker."""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import Any

from security_sink.common import KafkaMetadata, decode_message_key, payload_age_seconds
from security_sink.fault_injection import crash_once
from security_sink.kafka_batch_loop import BatchItem, KafkaBatchSinkLoop
from security_sink.metrics import MetricsServer, SinkMetrics, observe_kafka_position
from security_sink.resilience import (
    DlqPublisher,
    FailureRepository,
    ResilientProcessor,
    TerminalConsumptionRepository,
)
from security_sink.runtime import (
    ReusableMySQLConnectionFactory,
    kafka_config,
    kafka_producer_config,
    mysql_connection,
)
from security_sink.security_events import TOPIC, SecurityEventRepository, SecurityEventSink


LOGGER = logging.getLogger("security-event-sink")


def main() -> int:
    from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db_connections = ReusableMySQLConnectionFactory(
        mysql_connection,
        ping_interval=float(os.getenv("SECURITY_DB_PING_INTERVAL_SECONDS", "1")),
    )
    sink = SecurityEventSink(SecurityEventRepository(db_connections))
    config = kafka_config(
        "security-event-sink", "SECURITY_EVENT_CONSUMER_GROUP"
    )
    consumer_group = str(config["group.id"])
    consumer = Consumer(config)
    producer = Producer(kafka_producer_config(config))
    metrics = SinkMetrics(consumer_group)
    metrics.initialize_dlq(TOPIC)
    metrics_server = MetricsServer(
        metrics,
        os.getenv("METRICS_HOST", "127.0.0.1"),
        int(os.getenv("SECURITY_EVENT_METRICS_PORT", "9108")),
    )
    metrics_server.start()

    def send_dlq(topic: str, key: str | None, value: bytes) -> None:
        errors: list[str] = []

        def delivered(error: Any, _message: Any) -> None:
            if error is not None:
                errors.append(str(error))

        producer.produce(topic, key=key, value=value, on_delivery=delivered)
        remaining = producer.flush(10)
        if remaining or errors:
            raise RuntimeError("Kafka DLQ publish failed")

    processor = ResilientProcessor(
        FailureRepository(db_connections),
        TerminalConsumptionRepository(db_connections),
        DlqPublisher(send_dlq),
        on_retry=lambda metadata, details: (
            metrics.record_failure(metadata.topic, details.stage),
            metrics.record_retry(metadata.topic, details.stage),
        ),
        on_dlq=lambda metadata, details: (
            metrics.record_failure(metadata.topic, details.stage),
            metrics.record_dlq(metadata.topic, details.stage),
        ),
    )
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    consumer.subscribe([TOPIC])
    pending_observations: list[tuple[float, bytes]] = []

    def process_batch(items: list[BatchItem]):
        nonlocal pending_observations
        started = time.monotonic()
        values = [(raw_value, metadata) for _message, raw_value, metadata in items]
        try:
            results = sink.handle_batch(values)
            per_message = (time.monotonic() - started) / len(items)
            pending_observations = [(per_message, raw_value) for _message, raw_value, _ in items]
            return results
        except Exception:
            results = []
            pending_observations = []
            for _message, raw_value, metadata in items:
                item_started = time.monotonic()
                results.append(
                    processor.execute(
                        lambda raw_value=raw_value, metadata=metadata: sink.handle(
                            raw_value, metadata
                        ),
                        raw_value,
                        metadata,
                    )
                )
                pending_observations.append((time.monotonic() - item_started, raw_value))
            return results

    def processed(message: Any, result: Any) -> None:
        nonlocal pending_observations
        if not pending_observations:
            raise RuntimeError("message observation is missing after Kafka commit")
        processing_duration, raw_value = pending_observations.pop(0)
        metrics.record_message(
            message.topic(), result.duplicate or "processed", processing_duration,
            payload_age_seconds(raw_value),
        )

    def batch_processed(messages: list[Any], results: list[Any]) -> None:
        last = messages[-1]
        try:
            observe_kafka_position(metrics, consumer, last, TopicPartition)
        except Exception as exc:
            metrics.record_failure(last.topic(), "lag_collection")
            LOGGER.warning("Kafka lag collection failed: %s", type(exc).__name__)
        LOGGER.info(
            "processed security event batch count=%s duplicates=%s topic=%s "
            "partition=%s offsets=%s-%s",
            len(messages),
            sum(result.duplicate is not None for result in results),
            last.topic(),
            last.partition(),
            messages[0].offset(),
            last.offset(),
        )

    try:
        KafkaBatchSinkLoop(
            consumer,
            consumer_group=consumer_group,
            process_batch=process_batch,
            should_stop=lambda: stopping,
            is_partition_eof=lambda error: error.code() == KafkaError._PARTITION_EOF,
            before_commit=lambda message, _result: crash_once(
                "SECURITY_EVENT_TEST_CRASH_BEFORE_COMMIT_MARKER",
                "security_event_db_committed_before_kafka_commit",
                KafkaMetadata(
                    consumer_group=consumer_group,
                    topic=message.topic(),
                    partition=message.partition(),
                    offset=message.offset(),
                    key=decode_message_key(message.key()),
                ),
            ),
            on_committed=lambda messages, duration: metrics.record_commit(
                messages[-1].topic(), duration
            ),
            on_processed=processed,
            on_batch_processed=batch_processed,
            on_broker_error=lambda error, count: LOGGER.warning(
                "Kafka unavailable attempt=%s error=%s", count, type(error).__name__
            ) or metrics.record_failure(TOPIC, "broker_poll"),
            batch_size=int(os.getenv("SECURITY_SINK_BATCH_SIZE", "100")),
            consume_timeout=float(os.getenv("SECURITY_SINK_BATCH_WAIT_SECONDS", "0.1")),
        ).run()
    finally:
        consumer.close()
        metrics_server.close()
        db_connections.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
