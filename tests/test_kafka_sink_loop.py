from __future__ import annotations

import unittest
from typing import Any

from security_sink.common import KafkaMetadata, ProcessResult
from security_sink.kafka_loop import KafkaSinkLoop


class FakeError:
    def __init__(self, code: int) -> None:
        self._code = code

    def code(self) -> int:
        return self._code


class FakeMessage:
    def __init__(self, *, offset: int = 3, error: FakeError | None = None) -> None:
        self._offset = offset
        self._error = error

    def error(self) -> FakeError | None:
        return self._error

    def value(self) -> bytes:
        return b'{"event_id":"evt-1"}'

    def key(self) -> bytes:
        return b"evt-1"

    def topic(self) -> str:
        return "luck.security-events"

    def partition(self) -> int:
        return 0

    def offset(self) -> int:
        return self._offset


class FakeConsumer:
    def __init__(
        self,
        outcomes: list[FakeMessage | Exception | None],
        *,
        fail_commit: bool = False,
    ) -> None:
        self.outcomes = iter(outcomes)
        self.fail_commit = fail_commit
        self.commits: list[tuple[FakeMessage, bool]] = []

    def poll(self, _timeout: float) -> FakeMessage | None:
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def commit(self, *, message: FakeMessage, asynchronous: bool) -> None:
        if self.fail_commit:
            raise ConnectionError("commit interrupted")
        self.commits.append((message, asynchronous))


def make_loop(
    consumer: FakeConsumer,
    process: Any,
    *,
    delays: list[float] | None = None,
) -> KafkaSinkLoop:
    return KafkaSinkLoop(
        consumer,
        consumer_group="security-event-sink",
        process=process,
        should_stop=lambda: False,
        is_partition_eof=lambda error: error.code() == 1,
        sleeper=(delays.append if delays is not None else lambda _delay: None),
    )


class KafkaSinkLoopTests(unittest.TestCase):
    def test_broker_errors_back_off_then_recover_without_commit(self) -> None:
        delays: list[float] = []
        consumer = FakeConsumer(
            [FakeMessage(error=FakeError(2)), ConnectionError("broker down"), FakeMessage()]
        )
        processed: list[KafkaMetadata] = []

        make_loop(
            consumer,
            lambda _raw, item: processed.append(item) or ProcessResult(10),
            delays=delays,
        ).run(max_polls=3)

        self.assertEqual(delays, [1, 2])
        self.assertEqual(len(processed), 1)
        self.assertEqual(len(consumer.commits), 1)
        self.assertFalse(consumer.commits[0][1])

    def test_processing_failure_never_commits_offset(self) -> None:
        consumer = FakeConsumer([FakeMessage()])

        with self.assertRaisesRegex(ConnectionError, "DB unavailable"):
            make_loop(
                consumer,
                lambda _raw, _metadata: (_ for _ in ()).throw(
                    ConnectionError("DB unavailable")
                ),
            ).run(max_polls=1)

        self.assertEqual(consumer.commits, [])

    def test_restart_redelivery_is_idempotent_after_commit_interruption(self) -> None:
        persisted_offsets: set[int] = set()
        side_effects = 0

        def process(_raw: bytes, item: KafkaMetadata) -> ProcessResult:
            nonlocal side_effects
            if item.offset in persisted_offsets:
                return ProcessResult(None, duplicate="offset")
            persisted_offsets.add(item.offset)
            side_effects += 1
            return ProcessResult(31)

        first = FakeConsumer([FakeMessage(offset=9)], fail_commit=True)
        with self.assertRaisesRegex(ConnectionError, "commit interrupted"):
            make_loop(first, process).run(max_polls=1)

        restarted = FakeConsumer([FakeMessage(offset=9)])
        make_loop(restarted, process).run(max_polls=1)

        self.assertEqual(side_effects, 1)
        self.assertEqual(len(restarted.commits), 1)


if __name__ == "__main__":
    unittest.main()
