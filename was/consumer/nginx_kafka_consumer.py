"""Nginx access log를 수신한다. 실행: python -m consumer.nginx_kafka_consumer"""

import json
import logging
import os
import time
from pathlib import Path

from confluent_kafka import Consumer, KafkaException
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
TOPIC = "myohan.nginx.access"
GROUP_ID = "myohan-security-consumer"
DISPLAY_FIELDS = (
    "timestamp",
    "source",
    "request_id",
    "client_ip",
    "method",
    "uri",
    "status",
    "request_time",
)
logger = logging.getLogger(__name__)


def print_message(payload: bytes) -> None:
    record = json.loads(payload.decode("utf-8"))
    if not isinstance(record, dict):
        raise ValueError("JSON 객체 형태의 로그가 필요합니다.")
    print(
        json.dumps(
            {field: record.get(field) for field in DISPLAY_FIELDS},
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            "group.id": GROUP_ID,
            "auto.offset.reset": "latest",
        }
    )
    try:
        consumer.subscribe([TOPIC])
        logger.info("Consumer 시작: topic=%s, group=%s", TOPIC, GROUP_ID)
        while True:
            try:
                message = consumer.poll(timeout=1.0)
            except KafkaException as exc:
                logger.warning("Kafka 수신 오류: %s", exc)
                time.sleep(1.0)
                continue

            if message is None:
                continue
            if message.error():
                logger.warning("Kafka 메시지 오류: %s", message.error())
                continue

            payload = message.value()
            if payload is None:
                logger.warning("값이 없는 메시지를 건너뜁니다.")
                continue
            try:
                print_message(payload)
            except (UnicodeDecodeError, ValueError) as exc:
                # JSONDecodeError는 ValueError의 하위 클래스다.
                logger.warning("로그 파싱 실패: %s", exc)
    except KeyboardInterrupt:
        logger.info("종료 요청을 받았습니다.")
    finally:
        consumer.close()
        logger.info("Consumer 종료 완료")


if __name__ == "__main__":
    main()
