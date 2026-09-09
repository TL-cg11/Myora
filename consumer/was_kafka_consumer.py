"""WAS 로그 전용 Kafka Consumer. 실행: python -m consumer.was_kafka_consumer"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "schemas" / "was-log-v1.schema.json"
TOPIC = "myohan.was.app"
GROUP_ID = "myohan-security-was-consumer"
logger = logging.getLogger(__name__)

LogHandler = Callable[[dict[str, Any]], bool]


class InvalidWasLog(ValueError):
    """UTF-8, JSON 객체 또는 WAS 로그 스키마가 올바르지 않은 메시지."""


def load_schema_validator() -> Any:
    """프로세스 시작 시 JSON Schema와 validator를 한 번만 준비한다."""
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def parse_was_log(payload: bytes, validator: Any) -> dict[str, Any]:
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidWasLog(str(error)) from error
    if not isinstance(event, dict):
        raise InvalidWasLog("JSON 객체 형태의 WAS 로그가 필요합니다.")
    try:
        validator.validate(event)
    except Exception as error:
        raise InvalidWasLog(str(error)) from error
    return event


def handle_was_log(event: dict[str, Any]) -> bool:
    """PII 담당 모듈을 연결할 지점. 기본 handler는 offset을 commit하지 않는다."""
    summary = {
        key: event.get(key)
        for key in (
            "event_id",
            "request_id",
            "timestamp",
            "feature",
            "event_type",
            "severity",
            "status",
        )
        if key in event
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return False


def run(handler: LogHandler = handle_was_log) -> None:
    from confluent_kafka import Consumer, KafkaException

    load_dotenv(BASE_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    validator = load_schema_validator()
    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
            ),
            "group.id": GROUP_ID,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }
    )

    try:
        consumer.subscribe([TOPIC])
        logger.info("WAS Consumer 시작: topic=%s, group=%s", TOPIC, GROUP_ID)
        while True:
            try:
                message = consumer.poll(timeout=1.0)
            except KafkaException as error:
                logger.warning("Kafka 수신 오류: %s", error)
                time.sleep(1.0)
                continue

            if message is None:
                continue
            if message.error():
                logger.warning("Kafka 메시지 오류: %s", message.error())
                continue

            payload = message.value()
            if payload is None:
                logger.warning("값이 없는 WAS 메시지를 건너뜁니다.")
                continue

            try:
                event = parse_was_log(payload, validator)
                if handler(event):
                    # 마스킹 및 저장까지 성공한 handler만 True를 반환한다.
                    consumer.commit(message=message, asynchronous=False)
                else:
                    logger.warning(
                        "후속 처리 미연결: offset을 commit하지 않습니다. "
                        "topic=%s partition=%s offset=%s",
                        message.topic(),
                        message.partition(),
                        message.offset(),
                    )
            except InvalidWasLog as error:
                logger.warning(
                    "WAS 로그 검증 실패: topic=%s partition=%s offset=%s error=%s",
                    message.topic(),
                    message.partition(),
                    message.offset(),
                    error,
                )
            except Exception:
                logger.exception(
                    "WAS 로그 처리 실패: topic=%s partition=%s offset=%s",
                    message.topic(),
                    message.partition(),
                    message.offset(),
                )
    except KeyboardInterrupt:
        logger.info("종료 요청을 받았습니다.")
    finally:
        consumer.close()
        logger.info("WAS Consumer 종료 완료")


if __name__ == "__main__":
    run()
