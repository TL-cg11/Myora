"""Testable Kafka poll/process/commit loop shared by sink workers."""

from __future__ import annotations

import time
from typing import Any, Callable

from security_sink.common import KafkaMetadata, ProcessResult, decode_message_key


class KafkaSinkLoop:
    def __init__(
        self,
        consumer: Any,
        *,
        consumer_group: str,
        process: Callable[[bytes, KafkaMetadata], ProcessResult],
        should_stop: Callable[[], bool],
        is_partition_eof: Callable[[Any], bool],
        before_poll: Callable[[], None] | None = None,
        before_commit: Callable[[Any, ProcessResult], None] | None = None,
        on_committed: Callable[[Any, float], None] | None = None,
        on_processed: Callable[[Any, ProcessResult], None] | None = None,
        on_broker_error: Callable[[Exception | Any, int], None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        poll_timeout: float = 1.0,
        max_broker_delay: float = 30.0,
    ) -> None:
        self._consumer = consumer
        self._consumer_group = consumer_group
        self._process = process
        self._should_stop = should_stop
        self._is_partition_eof = is_partition_eof
        self._before_poll = before_poll
        self._before_commit = before_commit
        self._on_committed = on_committed
        self._on_processed = on_processed
        self._on_broker_error = on_broker_error
        self._sleeper = sleeper
        self._clock = clock
        self._poll_timeout = poll_timeout
        self._max_broker_delay = max_broker_delay

    def run(self, *, max_polls: int | None = None) -> None:
        polls = 0
        consecutive_broker_errors = 0
        while not self._should_stop():
            if max_polls is not None and polls >= max_polls:
                return
            if self._before_poll is not None:
                self._before_poll()
            polls += 1
            try:
                message = self._consumer.poll(self._poll_timeout)
            except Exception as exc:
                consecutive_broker_errors += 1
                self._broker_error(exc, consecutive_broker_errors)
                continue
            if message is None:
                continue
            error = message.error()
            if error:
                if self._is_partition_eof(error):
                    continue
                consecutive_broker_errors += 1
                self._broker_error(error, consecutive_broker_errors)
                continue

            consecutive_broker_errors = 0
            raw_value = message.value() or b""
            metadata = KafkaMetadata(
                consumer_group=self._consumer_group,
                topic=message.topic(),
                partition=message.partition(),
                offset=message.offset(),
                key=decode_message_key(message.key()),
            )
            result = self._process(raw_value, metadata)
            if self._before_commit is not None:
                self._before_commit(message, result)
            commit_started = self._clock()
            self._consumer.commit(message=message, asynchronous=False)
            if self._on_committed is not None:
                self._on_committed(message, self._clock() - commit_started)
            if self._on_processed is not None:
                self._on_processed(message, result)

    def _broker_error(self, error: Exception | Any, count: int) -> None:
        if self._on_broker_error is not None:
            self._on_broker_error(error, count)
        self._sleeper(min(2 ** (count - 1), self._max_broker_delay))
