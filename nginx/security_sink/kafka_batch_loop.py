"""Ordered Kafka micro-batch process/commit loop for sink workers."""

from __future__ import annotations

import time
from typing import Any, Callable

from security_sink.common import KafkaMetadata, ProcessResult, decode_message_key


BatchItem = tuple[Any, bytes, KafkaMetadata]


class KafkaBatchSinkLoop:
    def __init__(
        self,
        consumer: Any,
        *,
        consumer_group: str,
        process_batch: Callable[[list[BatchItem]], list[ProcessResult]],
        should_stop: Callable[[], bool],
        is_partition_eof: Callable[[Any], bool],
        before_poll: Callable[[], None] | None = None,
        before_commit: Callable[[Any, ProcessResult], None] | None = None,
        on_committed: Callable[[list[Any], float], None] | None = None,
        on_processed: Callable[[Any, ProcessResult], None] | None = None,
        on_batch_processed: Callable[[list[Any], list[ProcessResult]], None] | None = None,
        on_broker_error: Callable[[Exception | Any, int], None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        batch_size: int = 100,
        consume_timeout: float = 0.1,
        max_broker_delay: float = 30.0,
    ) -> None:
        if batch_size < 1 or consume_timeout <= 0:
            raise ValueError("batch_size and consume_timeout must be positive")
        self._consumer = consumer
        self._consumer_group = consumer_group
        self._process_batch = process_batch
        self._should_stop = should_stop
        self._is_partition_eof = is_partition_eof
        self._before_poll = before_poll
        self._before_commit = before_commit
        self._on_committed = on_committed
        self._on_processed = on_processed
        self._on_batch_processed = on_batch_processed
        self._on_broker_error = on_broker_error
        self._sleeper = sleeper
        self._clock = clock
        self._batch_size = batch_size
        self._consume_timeout = consume_timeout
        self._max_broker_delay = max_broker_delay

    def run(self, *, max_batches: int | None = None) -> None:
        batches = 0
        consecutive_broker_errors = 0
        while not self._should_stop():
            if max_batches is not None and batches >= max_batches:
                return
            if self._before_poll is not None:
                self._before_poll()
            batches += 1
            try:
                messages = self._consumer.consume(
                    num_messages=self._batch_size, timeout=self._consume_timeout
                )
            except Exception as exc:
                consecutive_broker_errors += 1
                self._broker_error(exc, consecutive_broker_errors)
                continue
            items: list[BatchItem] = []
            for message in messages:
                error = message.error()
                if error:
                    if not self._is_partition_eof(error):
                        consecutive_broker_errors += 1
                        self._broker_error(error, consecutive_broker_errors)
                    continue
                raw_value = message.value() or b""
                items.append(
                    (
                        message,
                        raw_value,
                        KafkaMetadata(
                            consumer_group=self._consumer_group,
                            topic=message.topic(),
                            partition=message.partition(),
                            offset=message.offset(),
                            key=decode_message_key(message.key()),
                        ),
                    )
                )
            if not items:
                continue
            consecutive_broker_errors = 0
            partition_batches: dict[tuple[str, int], list[BatchItem]] = {}
            for item in items:
                partition_batches.setdefault(
                    (item[2].topic, item[2].partition), []
                ).append(item)
            for partition_items in partition_batches.values():
                partition_items.sort(key=lambda item: item[2].offset)
                results = self._process_batch(partition_items)
                if len(results) != len(partition_items):
                    raise RuntimeError("batch processor returned an unexpected result count")
                last_message = partition_items[-1][0]
                if self._before_commit is not None:
                    self._before_commit(last_message, results[-1])
                commit_started = self._clock()
                self._consumer.commit(message=last_message, asynchronous=False)
                if self._on_committed is not None:
                    self._on_committed(
                        [item[0] for item in partition_items],
                        self._clock() - commit_started,
                    )
                if self._on_processed is not None:
                    for item, result in zip(partition_items, results):
                        self._on_processed(item[0], result)
                if self._on_batch_processed is not None:
                    self._on_batch_processed(
                        [item[0] for item in partition_items], results
                    )

    def _broker_error(self, error: Exception | Any, count: int) -> None:
        if self._on_broker_error is not None:
            self._on_broker_error(error, count)
        self._sleeper(min(2 ** (count - 1), self._max_broker_delay))
