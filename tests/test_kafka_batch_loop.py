from __future__ import annotations

import unittest

from security_sink.common import ProcessResult
from security_sink.kafka_batch_loop import KafkaBatchSinkLoop


class Message:
    def __init__(self, offset: int, *, partition: int = 0) -> None:
        self._offset = offset
        self._partition = partition

    def error(self):
        return None

    def value(self) -> bytes:
        return f'{{"offset":{self._offset}}}'.encode()

    def key(self) -> bytes:
        return str(self._offset).encode()

    def topic(self) -> str:
        return "topic"

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset


class Consumer:
    def __init__(self, batches: list[list[Message]]) -> None:
        self.batches = iter(batches)
        self.commits: list[tuple[int, bool]] = []

    def consume(self, *, num_messages: int, timeout: float) -> list[Message]:
        self.request = (num_messages, timeout)
        return next(self.batches, [])

    def commit(self, *, message: Message, asynchronous: bool) -> None:
        self.commits.append((message.offset(), asynchronous))


class KafkaBatchSinkLoopTests(unittest.TestCase):
    def test_ordered_batch_is_processed_then_committed_at_highest_offset(self) -> None:
        consumer = Consumer([[Message(4), Message(5), Message(6)]])
        processed: list[int] = []
        commits: list[tuple[list[int], float]] = []
        clock = iter([10.0, 10.02])
        loop = KafkaBatchSinkLoop(
            consumer,
            consumer_group="group",
            process_batch=lambda items: [ProcessResult(None) for _ in items],
            should_stop=lambda: False,
            is_partition_eof=lambda _error: False,
            on_committed=lambda messages, duration: commits.append(
                ([message.offset() for message in messages], duration)
            ),
            on_processed=lambda message, _result: processed.append(message.offset()),
            clock=lambda: next(clock),
        )

        loop.run(max_batches=1)

        self.assertEqual(consumer.commits, [(6, False)])
        self.assertEqual(processed, [4, 5, 6])
        self.assertEqual(commits, [([4, 5, 6], 0.019999999999999574)])

    def test_different_partitions_are_processed_and_committed_separately(self) -> None:
        consumer = Consumer([[Message(2, partition=0), Message(7, partition=1)]])
        sizes: list[int] = []
        loop = KafkaBatchSinkLoop(
            consumer,
            consumer_group="group",
            process_batch=lambda items: sizes.append(len(items)) or [ProcessResult(None)],
            should_stop=lambda: False,
            is_partition_eof=lambda _error: False,
        )

        loop.run(max_batches=1)

        self.assertEqual(sizes, [1, 1])
        self.assertEqual(consumer.commits, [(2, False), (7, False)])

    def test_processing_failure_never_commits_batch(self) -> None:
        consumer = Consumer([[Message(1), Message(2)]])

        def fail(_items):
            raise RuntimeError("failed")

        loop = KafkaBatchSinkLoop(
            consumer,
            consumer_group="group",
            process_batch=fail,
            should_stop=lambda: False,
            is_partition_eof=lambda _error: False,
        )

        with self.assertRaises(RuntimeError):
            loop.run(max_batches=1)
        self.assertEqual(consumer.commits, [])

    def test_before_commit_crash_leaves_whole_batch_uncommitted(self) -> None:
        consumer = Consumer([[Message(10), Message(11)]])
        processed: list[int] = []

        def crash(_message, _result):
            raise RuntimeError("injected crash")

        loop = KafkaBatchSinkLoop(
            consumer,
            consumer_group="group",
            process_batch=lambda items: [ProcessResult(None) for _ in items],
            should_stop=lambda: False,
            is_partition_eof=lambda _error: False,
            before_commit=crash,
            on_processed=lambda message, _result: processed.append(message.offset()),
        )

        with self.assertRaises(RuntimeError):
            loop.run(max_batches=1)
        self.assertEqual(consumer.commits, [])
        self.assertEqual(processed, [])


if __name__ == "__main__":
    unittest.main()
