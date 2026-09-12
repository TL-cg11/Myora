# 결과 발행이 끝난 뒤에만 offset을 commit하는지 가짜 Kafka client로 검사한다.
import json
from pathlib import Path
import unittest

from adapter.config import load_settings
from adapter.kafka_runner import KafkaBridge, PublishError
from adapter.pipeline import MaskingPipeline
from adapter.policy import load_policy

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = {
    "MASKING_PSEUDONYM_KEY": "unit-test-pseudonym-key-0123456789",
    "ADAPTER_DEFAULT_ENVIRONMENT": "test",
    "ADAPTER_PUBLISH_ATTEMPTS": "2",
}


def example(name: str) -> dict:
    return json.loads(
        (ROOT.parents[1] / "schemas" / "examples" / name).read_text(encoding="utf-8")
    )


class FakeMessage:
    def __init__(self, value: bytes, *, topic="myohan.was.app", partition=0, offset=1,
                 key=b"req-1", error=None):
        self._value, self._topic = value, topic
        self._partition, self._offset = partition, offset
        self._key, self._error = key, error

    def value(self):
        return self._value

    def key(self):
        return self._key

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def error(self):
        return self._error


class FakeConsumer:
    def __init__(self, messages):
        self._messages = list(messages)
        self.subscribed = None
        self.committed = []
        self.closed = False

    def subscribe(self, topics):
        self.subscribed = topics

    def poll(self, _timeout):
        return self._messages.pop(0) if self._messages else None

    def commit(self, *, message, asynchronous):
        self.committed.append((message.topic(), message.offset(), asynchronous))

    def close(self):
        self.closed = True


class FakeProducer:
    def __init__(self, *, delivery_error=None):
        self.produced = []
        self._delivery_error = delivery_error
        self._callbacks = []

    def produce(self, topic, *, key, value, callback):
        self.produced.append((topic, key, json.loads(value.decode("utf-8"))))
        self._callbacks.append(callback)

    def poll(self, _timeout):
        return 0

    def flush(self, _timeout):
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback(self._delivery_error)
        return 0


def build_bridge(messages, *, producer=None):
    settings = load_settings(ENVIRONMENT)
    pipeline = MaskingPipeline(settings, load_policy())
    consumer = FakeConsumer(messages)
    producer = producer or FakeProducer()
    return KafkaBridge(settings, pipeline, consumer=consumer, producer=producer,
                       sleeper=lambda _seconds: None), consumer, producer


def encode(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False).encode("utf-8")


class CommitOrderTest(unittest.TestCase):
    def test_offset_is_committed_after_the_result_is_published(self):
        message = FakeMessage(encode(example("was-api-request.json")), offset=11)
        bridge, consumer, producer = build_bridge([message])
        counts = bridge.run(max_polls=2)
        self.assertEqual([topic for topic, _, _ in producer.produced], ["myohan.masked-logs"])
        self.assertEqual(consumer.committed, [("myohan.was.app", 11, False)])
        self.assertEqual(counts, {"read": 1, "masked": 1, "security_events": 0, "failed": 0})
        self.assertTrue(consumer.closed)
        self.assertEqual(consumer.subscribed, ["myohan.was.app", "myohan.nginx.access"])

    def test_detected_log_publishes_both_result_topics(self):
        record = example("was-ai-request.json")
        record["input"]["question"] = "제 번호는 010-1234-5678이에요"
        bridge, consumer, producer = build_bridge([FakeMessage(encode(record))])
        counts = bridge.run(max_polls=2)
        self.assertEqual(
            [topic for topic, _, _ in producer.produced],
            ["myohan.masked-logs", "myohan.security-events"],
        )
        self.assertEqual(counts["security_events"], 1)
        self.assertEqual(len(consumer.committed), 1)

    def test_failed_message_is_committed_after_the_dead_letter_is_published(self):
        bridge, consumer, producer = build_bridge([FakeMessage(b"{broken", offset=4)])
        counts = bridge.run(max_polls=2)
        self.assertEqual([topic for topic, _, _ in producer.produced], ["myohan.dead-letter"])
        self.assertEqual(consumer.committed, [("myohan.was.app", 4, False)])
        self.assertEqual(counts["failed"], 1)

    def test_publish_failure_stops_the_loop_without_committing(self):
        producer = FakeProducer(delivery_error="broker down")
        bridge, consumer, _ = build_bridge(
            [FakeMessage(encode(example("was-api-request.json")))], producer=producer
        )
        with self.assertRaises(PublishError):
            bridge.run(max_polls=2)
        self.assertEqual(consumer.committed, [])
        self.assertTrue(consumer.closed)


class LoopControlTest(unittest.TestCase):
    def test_stop_request_ends_the_loop(self):
        bridge, consumer, _ = build_bridge([])
        bridge.stop()
        bridge.run()
        self.assertTrue(consumer.closed)

    def test_broker_errors_are_retried_instead_of_crashing(self):
        class FlakyConsumer(FakeConsumer):
            def __init__(self):
                super().__init__([])
                self.polls = 0

            def poll(self, _timeout):
                self.polls += 1
                if self.polls == 1:
                    raise RuntimeError("broker unreachable")
                return None

        settings = load_settings(ENVIRONMENT)
        consumer = FlakyConsumer()
        bridge = KafkaBridge(settings, MaskingPipeline(settings, load_policy()),
                             consumer=consumer, producer=FakeProducer(),
                             sleeper=lambda _seconds: None)
        counts = bridge.run(max_polls=3)
        self.assertEqual(counts["read"], 0)
        self.assertEqual(consumer.polls, 3)


if __name__ == "__main__":
    unittest.main()
