# Kafka 연결부: 원본 topic 소비 → 파이프라인 → 결과 발행 → offset commit 순서를 지킨다.
"""Consume raw log topics, publish masked results, then commit the input offset."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from adapter.config import Settings
from adapter.pipeline import MaskingPipeline, OutboundMessage

logger = logging.getLogger("adapter.kafka")


class PublishError(RuntimeError):
    """결과를 모두 발행하지 못한 상태. offset을 commit하면 안 된다."""


# key가 없거나 너무 길면 partition 배정에 쓰지 않는다.
def _encode_key(key: str | None) -> bytes | None:
    if not key:
        return None
    return key.encode("utf-8")[:128]


# UTF-8 JSON 한 줄로 직렬화한다. NaN/Infinity는 계약에서 허용하지 않는다.
def _encode_value(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


class KafkaBridge:
    """원본 topic과 결과 topic을 잇는 실행기. 테스트에서는 가짜 client를 주입한다."""

    def __init__(
        self,
        settings: Settings,
        pipeline: MaskingPipeline,
        *,
        consumer: Any,
        producer: Any,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._pipeline = pipeline
        self._consumer = consumer
        self._producer = producer
        self._sleeper = sleeper
        self._stopping = False
        self.counts = {"read": 0, "masked": 0, "security_events": 0, "failed": 0}

    # SIGTERM 등으로 현재 메시지 처리를 마친 뒤 종료하도록 요청한다.
    def stop(self) -> None:
        self._stopping = True

    # 결과 발행이 끝난 메시지만 commit한다. 발행에 실패하면 루프를 멈춘다.
    def run(self, *, max_polls: int | None = None) -> dict[str, int]:
        self._consumer.subscribe(list(self._settings.input_topics))
        logger.info(
            "마스킹 어댑터 시작: topics=%s group=%s",
            ", ".join(self._settings.input_topics),
            self._settings.group_id,
        )
        polls = 0
        broker_errors = 0
        try:
            while not self._stopping:
                if max_polls is not None and polls >= max_polls:
                    break
                polls += 1
                try:
                    message = self._consumer.poll(self._settings.poll_timeout)
                except Exception as error:  # broker 접속 실패는 재시도로 회복한다.
                    broker_errors += 1
                    logger.warning("Kafka 수신 오류: %s", error)
                    self._sleeper(min(2 ** (broker_errors - 1), 30))
                    continue
                if message is None:
                    continue
                error = message.error()
                if error is not None:
                    logger.warning("Kafka 메시지 오류: %s", error)
                    continue
                broker_errors = 0
                self._handle(message)
        finally:
            self._producer.flush(self._settings.flush_timeout)
            self._consumer.close()
            logger.info("마스킹 어댑터 종료: %s", json.dumps(self.counts))
        return self.counts

    # 메시지 한 건을 처리하고 결과 발행이 확인된 뒤에만 offset을 넘긴다.
    def _handle(self, message: Any) -> None:
        self.counts["read"] += 1
        raw = message.value() or b""
        key = message.key()
        if isinstance(key, bytes):
            key = key.decode("utf-8", "replace")
        result = self._pipeline.handle(
            raw,
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            message_key=key[:128] if key else None,
        )
        self._publish(result.messages)
        self._consumer.commit(message=message, asynchronous=False)
        if result.failed:
            self.counts["failed"] += 1
            logger.warning(
                "처리 실패를 dead-letter로 보냈습니다: code=%s topic=%s partition=%s offset=%s",
                result.error_code,
                message.topic(),
                message.partition(),
                message.offset(),
            )
            return
        self.counts["masked"] += 1
        if len(result.messages) > 1:
            self.counts["security_events"] += 1

    # 실패한 메시지만 다시 보낸다. 재시도 후에도 남으면 commit하지 않고 중단한다.
    def _publish(self, messages: tuple[OutboundMessage, ...]) -> None:
        pending = list(messages)
        for attempt in range(1, self._settings.publish_attempts + 1):
            if not pending:
                return
            pending = self._publish_once(pending)
            if pending:
                logger.warning("발행 실패 %s건, 재시도 %s회차", len(pending), attempt)
                self._sleeper(min(2 ** (attempt - 1), 10))
        if pending:
            raise PublishError("결과 발행에 실패해 offset을 commit하지 않습니다.")

    # 한 번 발행하고 전달 보고를 기다린 뒤 실패한 메시지를 돌려준다.
    def _publish_once(self, messages: list[OutboundMessage]) -> list[OutboundMessage]:
        failed: list[OutboundMessage] = []

        def report(message: OutboundMessage):
            def callback(error: Any, _: Any = None) -> None:
                if error is not None:
                    logger.error("결과 발행 실패: topic=%s error=%s", message.topic, error)
                    failed.append(message)

            return callback

        for message in messages:
            try:
                self._producer.produce(
                    message.topic,
                    key=_encode_key(message.key),
                    value=_encode_value(message.value),
                    callback=report(message),
                )
            except BufferError:
                # 큐가 가득 차면 전송이 끝날 때까지 기다린 뒤 다음 시도에 다시 넣는다.
                failed.append(message)
                self._producer.poll(1.0)
        remaining = self._producer.flush(self._settings.flush_timeout)
        if remaining:
            raise PublishError("발행 확인을 기다리는 동안 시간이 지났습니다.")
        return failed


# 실제 confluent-kafka client를 만든다. 테스트에서는 사용하지 않는다.
def build_clients(settings: Settings) -> tuple[Any, Any]:
    from confluent_kafka import Consumer, Producer

    return Consumer(settings.consumer_config()), Producer(settings.producer_config())
