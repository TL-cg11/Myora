# 파일 실행기: JSONL을 한 줄씩 읽어 정상 로그·보안 이벤트·실패 기록을 나눈다.
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from .engine import process_log
from .jsonio import loads
from .models import ProcessingFailure, ProcessingResult

# 한 행을 무제한으로 메모리에 읽지 않도록 바이트 크기를 제한한다.
MAX_LINE_BYTES = 1_000_000


# 새 결과 폴더에 세 JSONL을 생성하고 읽기·성공·탐지·실패 건수를 반환한다.
def run(source: Path, output: Path) -> dict:
    # An exclusive fresh directory prevents accidental overwrite or raw/output aliasing.
    key_text = os.environ.get("DETECTOR_FINGERPRINT_KEY")
    key = key_text.encode("utf-8") if key_text else None
    if key is not None and len(key) < 32:
        raise ValueError("INVALID_FINGERPRINT_KEY")
    counts = {"read": 0, "masked": 0, "security_events": 0, "failed": 0}
    with source.open("rb") as incoming:
        output.mkdir(parents=True, exist_ok=False)
        with (output / "masked-logs.jsonl").open("x", encoding="utf-8") as masked, \
             (output / "security-events.jsonl").open("x", encoding="utf-8") as events, \
             (output / "dead-letter.jsonl").open("x", encoding="utf-8") as failures:
            while True:
                line = incoming.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break
                counts["read"] += 1
                # 너무 긴 행은 줄 끝까지 버려 다음 조각이 새 로그로 오인되지 않게 한다.
                if len(line) > MAX_LINE_BYTES:
                    while line and not line.endswith(b"\n"):
                        line = incoming.readline(MAX_LINE_BYTES + 1)
                    result = ProcessingResult(failure=ProcessingFailure("1.0", "LINE_TOO_LARGE", "DECODE", False))
                else:
                    try:
                        data = loads(line.decode("utf-8"))
                    except (ValueError, UnicodeError, RecursionError):
                        result = ProcessingResult(failure=ProcessingFailure("1.0", "INVALID_JSON", "DECODE", False))
                    else:
                        result = process_log(data, fingerprint_key=key)
                for value, stream, count_key in ((result.masked_log, masked, "masked"),
                                                  (result.security_event, events, "security_events"),
                                                  (result.failure, failures, "failed")):
                    if value is not None:
                        payload = asdict(value)
                        # 원문 대신 행 번호만 남겨 제한된 입력 파일에서 재처리 대상을 찾는다.
                        if count_key == "failed":
                            payload["line_number"] = counts["read"]
                        stream.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
                        counts[count_key] += 1
    return counts


# 명령행 인자를 해석하고 처리 결과에 맞는 종료 코드를 반환한다.
def main():
    parser = argparse.ArgumentParser(description="Offline log detector; output directory must not exist.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        counts = run(args.input, args.output_dir)
    except (OSError, ValueError):
        print("INPUT_OUTPUT_OR_CONFIG_ERROR: check paths, new output directory and key length.", file=sys.stderr)
        return 2
    print(json.dumps(counts))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
