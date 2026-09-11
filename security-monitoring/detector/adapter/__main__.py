# 어댑터 실행기: python -m adapter 로 Kafka 소비·발행 루프를 시작한다.
import argparse
import json
import logging
from pathlib import Path
import signal
import sys

from adapter.config import ConfigError, load_settings
from adapter.kafka_runner import KafkaBridge, PublishError, build_clients
from adapter.pipeline import MaskingPipeline
from adapter.policy import PolicyError, load_policy
from app.rules.ner import NERConfigurationError
from app.rules.pii_context import PIIContextConfigurationError


# .env는 선택 사항이다. python-dotenv가 없으면 환경변수만 사용한다.
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")


# Kafka 없이 마스킹 결과만 확인한다. 한 줄에 원본 로그 JSON 하나를 읽는다.
def dry_run(pipeline: MaskingPipeline, source: str, topic: str) -> int:
    stream = sys.stdin if source == "-" else Path(source).open(encoding="utf-8")
    failed = 0
    try:
        for offset, line in enumerate(stream):
            if not line.strip():
                continue
            result = pipeline.handle(
                line.strip().encode("utf-8"), topic=topic, partition=0, offset=offset
            )
            failed += 1 if result.failed else 0
            for message in result.messages:
                print(f"### topic={message.topic} key={message.key}")
                print(json.dumps(message.value, ensure_ascii=False, indent=2))
    finally:
        if stream is not sys.stdin:
            stream.close()
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mask raw Kafka logs and publish the consumer contracts."
    )
    parser.add_argument("--policy", default=None, help="마스킹 정책 파일 경로")
    parser.add_argument("--max-polls", type=int, default=None, help="지정 횟수만 poll하고 종료")
    parser.add_argument(
        "--dry-run",
        metavar="JSONL",
        default=None,
        help="Kafka에 연결하지 않고 파일 또는 -(표준 입력)의 로그를 마스킹해 출력한다",
    )
    parser.add_argument(
        "--dry-run-topic",
        default="myohan.was.app",
        help="--dry-run 입력을 어느 원본 topic으로 볼지 지정한다",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_env()
    try:
        settings = load_settings()
        policy = load_policy(args.policy)
    except (ConfigError, PolicyError) as error:
        print(f"CONFIG_ERROR: {error}", file=sys.stderr)
        return 2
    try:
        pipeline = MaskingPipeline(settings, policy)
    except (NERConfigurationError, PIIContextConfigurationError) as error:
        print(f"CONFIG_ERROR: {error}", file=sys.stderr)
        return 2
    if args.dry_run is not None:
        try:
            return dry_run(pipeline, args.dry_run, args.dry_run_topic)
        except OSError as error:
            print(f"INPUT_ERROR: {error}", file=sys.stderr)
            return 2

    consumer, producer = build_clients(settings)
    bridge = KafkaBridge(settings, pipeline, consumer=consumer, producer=producer)
    # 처리 중인 메시지를 마친 뒤 종료해 commit되지 않은 결과가 남지 않게 한다.
    for name in ("SIGINT", "SIGTERM"):
        received = getattr(signal, name, None)
        if received is not None:
            signal.signal(received, lambda *_: bridge.stop())

    try:
        counts = bridge.run(max_polls=args.max_polls)
    except PublishError as error:
        print(f"PUBLISH_ERROR: {error}", file=sys.stderr)
        return 1
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
