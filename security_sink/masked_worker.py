#!/usr/bin/env python3
"""Run the ``myohan.masked-logs`` Kafka-to-Loki worker."""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Any

from security_sink.common import KafkaMetadata
from security_sink.fault_injection import crash_once
from security_sink.kafka_loop import KafkaSinkLoop
from security_sink.metrics import MetricsServer, SinkMetrics, observe_kafka_position
from security_sink.masked_logs import TOPIC, ConsumptionRepository, LokiClient, MaskedLogSink
from security_sink.resilience import (
    DlqPublisher,
    FailureRepository,
    FilesystemBuffer,
    ResilientProcessor,
    TerminalConsumptionRepository,
)
from security_sink.runtime import (
    kafka_config,
    kafka_producer_config,
    mysql_connection,
    required,
)


LOGGER = logging.getLogger("masked-log-sink")


def main() -> int:
    from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = kafka_config("masked-log-sink", "MASKED_LOG_CONSUMER_GROUP")
    consumer_group = str(config["group.id"])
    sink = MaskedLogSink(
        ConsumptionRepository(mysql_connection),
        LokiClient(
            required("LOKI_URL"),
            timeout=float(os.getenv("LOKI_PUSH_TIMEOUT_SECONDS", "5")),
        ),
        after_loki_push=lambda metadata: crash_once(
            "MASKED_LOG_TEST_CRASH_AFTER_LOKI_MARKER",
            "loki_pushed_before_consumption_and_kafka_commit",
            metadata,
        ),
    )
    consumer = Consumer(config)
    producer = Producer(kafka_producer_config(config))
    metrics = SinkMetrics(consumer_group)
    metrics.initialize_dlq(TOPIC)
    metrics_server = MetricsServer(
        metrics,
        os.getenv("METRICS_HOST", "127.0.0.1"),
        int(os.getenv("MASKED_LOG_METRICS_PORT", "9109")),
    )
    metrics_server.start()
    failures = FailureRepository(mysql_connection)
    buffer = FilesystemBuffer(
        Path(
            os.getenv(
                "MASKED_LOG_BUFFER_DIR",
                "/var/lib/luck-security-sink/masked-log-buffer",
            )
        ),
        max_bytes=int(os.getenv("MASKED_LOG_BUFFER_MAX_BYTES", "1073741824")),
    )

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
        failures,
        TerminalConsumptionRepository(mysql_connection),
        DlqPublisher(send_dlq),
        buffer=buffer,
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
    replay_interval = float(os.getenv("MASKED_LOG_BUFFER_REPLAY_SECONDS", "60"))
    next_replay = 0.0

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    consumer.subscribe([TOPIC])

    def replay_buffer() -> None:
        nonlocal next_replay
        if time.monotonic() < next_replay:
            return
        for entry in buffer.entries():
            try:
                sink.replay_buffered(entry.raw_value, entry.metadata)
                failures.mark_recovered(entry.metadata)
                buffer.acknowledge(entry)
                LOGGER.info(
                    "replayed buffered masked log partition=%s offset=%s",
                    entry.metadata.partition,
                    entry.metadata.offset,
                )
            except Exception as exc:
                LOGGER.warning(
                    "masked log buffer replay paused: %s", type(exc).__name__
                )
                break
        next_replay = time.monotonic() + replay_interval

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
            "processed masked log duplicate=%s topic=%s partition=%s offset=%s",
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
            before_poll=replay_buffer,
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
