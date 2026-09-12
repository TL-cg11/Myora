#!/usr/bin/env python3
"""Run the ``myohan.security-events`` Kafka-to-MariaDB worker."""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import Any

from security_sink.common import KafkaMetadata
from security_sink.kafka_loop import KafkaSinkLoop
from security_sink.metrics import MetricsServer, SinkMetrics, observe_kafka_position
from security_sink.resilience import (
    DlqPublisher,
    FailureRepository,
    ResilientProcessor,
    TerminalConsumptionRepository,
)
from security_sink.runtime import kafka_config, kafka_producer_config, mysql_connection
from security_sink.security_events import TOPIC, SecurityEventRepository, SecurityEventSink


LOGGER = logging.getLogger("security-event-sink")


def main() -> int:
    from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sink = SecurityEventSink(SecurityEventRepository(mysql_connection))
    config = kafka_config(
        "security-event-sink", "SECURITY_EVENT_CONSUMER_GROUP"
    )
    consumer_group = str(config["group.id"])
    consumer = Consumer(config)
    producer = Producer(kafka_producer_config(config))
    metrics = SinkMetrics(consumer_group)
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
        FailureRepository(mysql_connection),
        TerminalConsumptionRepository(mysql_connection),
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

    def process(raw_value: bytes, metadata: KafkaMetadata):
        started = time.monotonic()
        result = processor.execute(
            lambda: sink.handle(raw_value, metadata), raw_value, metadata
        )
        metrics.record_message(
            metadata.topic, result.duplicate or "processed", time.monotonic() - started
        )
        return result

    def processed(message: Any, result: Any) -> None:
        try:
            observe_kafka_position(metrics, consumer, message, TopicPartition)
        except Exception as exc:
            metrics.record_failure(message.topic(), "lag_collection")
            LOGGER.warning("Kafka lag collection failed: %s", type(exc).__name__)
        LOGGER.info(
            "processed security event db_id=%s duplicate=%s topic=%s partition=%s offset=%s",
            result.event_db_id,
            result.duplicate or "no",
            message.topic(),
            message.partition(),
            message.offset(),
        )

    try:
        KafkaSinkLoop(
            consumer,
            consumer_group=consumer_group,
            process=process,
            should_stop=lambda: stopping,
            is_partition_eof=lambda error: error.code() == KafkaError._PARTITION_EOF,
            on_processed=processed,
            on_broker_error=lambda error, count: LOGGER.warning(
                "Kafka unavailable attempt=%s error=%s", count, type(error).__name__
            ) or metrics.record_failure(TOPIC, "broker_poll"),
        ).run()
    finally:
        consumer.close()
        metrics_server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
