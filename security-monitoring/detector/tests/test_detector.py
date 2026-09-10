# 회귀 테스트: 정상/민감 입력, 재처리, 실패 시 원문 노출 방지, 파일 입출력을 검증한다.
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.__main__ import run
from app.engine import process_log
from app.evaluation import evaluate
from app.hashing import fingerprint
from app.masking import mask
from app.models import Detection, NormalizedLog
from app.rules.ner import TransformersNERRecognizer

FIXTURES = json.loads((Path(__file__).parent / "fixtures/cases.json").read_text(encoding="utf-8"))


# 각 테스트가 fixture 원본을 바꾸지 않도록 독립적인 깊은 복사본을 만든다.
def sample():
    return deepcopy(FIXTURES["cases"][0]["input"])


# 정답 fixture와 평가 집계 회귀 테스트.
class FixtureTests(unittest.TestCase):
    # 43개 합성 사례에서 규칙·치환 결과·위험도와 입력 불변성을 함께 확인한다.
    def test_all_fixtures(self):
        for case in FIXTURES["cases"]:
            with self.subTest(case=case["name"]):
                original = deepcopy(case["input"])
                result = process_log(original)
                self.assertIsNone(result.failure)
                expected = case["expected"]
                self.assertEqual(set(result.masked_log.detected_rules), set(expected["rules"]))
                self.assertEqual(result.masked_log.body_masked, expected["masked_body"])
                if "masked_attributes" in expected:
                    self.assertEqual(result.masked_log.attributes, expected["masked_attributes"])
                for key in ("risk_level", "risk_score"):
                    if key in expected:
                        self.assertEqual(getattr(result.masked_log, key), expected[key])
                self.assertEqual(original, case["input"])
                self.assertEqual(result.security_event is not None, bool(expected["rules"]))

    # 합성 회귀 데이터에 대한 평가 통과를 확인한다. 운영 정확도를 보장하는 테스트는 아니다.
    def test_evaluation(self):
        report = evaluate(FIXTURES)
        self.assertEqual(report["failed_case_numbers"], [])
        self.assertEqual(report["micro"]["f1"], 1)

    # 정답 규칙을 일부러 바꿔 오탐과 미탐이 각각 계산되는지 확인한다.
    def test_evaluation_counts_false_positive_and_negative(self):
        case = deepcopy(FIXTURES["cases"][6])
        case["expected"]["rules"] = ["EMAIL_ADDRESS"]
        report = evaluate({"dataset_version": "test", "cases": [case]})
        self.assertEqual(report["micro"]["fp"], 1)
        self.assertEqual(report["micro"]["fn"], 1)
        self.assertEqual(report["failed_case_numbers"], [1])


# 처리 엔진의 오류·보안·재처리 동작 테스트.
class EngineTests(unittest.TestCase):
    def test_ner_masks_free_text_person_and_location(self):
        text = "김민수는 서울역에서 기다립니다"

        def inference(chunk):
            return [
                {"entity_group": "PS", "score": 0.98,
                 "start": chunk.index("김민수"), "end": chunk.index("김민수") + 3},
                {"entity_group": "LC", "score": 0.96,
                 "start": chunk.index("서울역"), "end": chunk.index("서울역") + 3},
            ]

        recognizer = TransformersNERRecognizer("fake", inference=inference)
        data = sample()
        data["body"] = text
        result = process_log(data, ner_recognizer=recognizer)
        self.assertIsNone(result.failure)
        self.assertEqual(
            result.masked_log.body_masked,
            "[REDACTED_PERSON]는 [REDACTED_LOCATION]에서 기다립니다",
        )
        self.assertEqual(
            result.masked_log.detected_rules, ["LOCATION", "PERSON_NAME"]
        )

    def test_ner_threshold_and_unknown_labels_are_ignored(self):
        def inference(_):
            return [
                {"entity_group": "PS", "score": 0.70, "start": 0, "end": 3},
                {"entity_group": "OG", "score": 0.99, "start": 4, "end": 7},
            ]

        recognizer = TransformersNERRecognizer(
            "fake", threshold=0.85, inference=inference
        )
        self.assertEqual(recognizer.detect("김민수 회사원"), [])

    def test_ner_does_not_remask_existing_redaction_marker(self):
        text = "고객 [REDACTED_PERSON] 확인"

        def inference(chunk):
            start = chunk.index("REDACTED_PERSON")
            return [{"entity_group": "PS", "score": 0.99,
                     "start": start, "end": start + len("REDACTED_PERSON")}]

        recognizer = TransformersNERRecognizer("fake", inference=inference)
        self.assertEqual(recognizer.detect(text), [])

    def test_ner_failure_fails_closed_without_raw_output(self):
        secret_name = "김민수"

        def inference(_):
            raise RuntimeError(secret_name)

        data = sample()
        data["body"] = f"고객은 {secret_name}입니다"
        recognizer = TransformersNERRecognizer("fake", inference=inference)
        result = process_log(data, ner_recognizer=recognizer)
        self.assertIsNone(result.masked_log)
        self.assertEqual(result.failure.error_code, "PROCESSING_ERROR")
        self.assertNotIn(secret_name, json.dumps(result.to_dict(), ensure_ascii=False))

    # 재처리 ID 유지, UTC 변환, 같은 규칙의 탐지 묶음 및 C용 필드를 확인한다.
    def test_stable_ids_and_schema_mapping(self):
        data = sample()
        data["body"] = "010-1234-5678 tester@example.com 010-1234-5678"
        a = process_log(data).security_event
        b = process_log(data).security_event
        self.assertEqual(a.event_id, b.event_id)
        self.assertEqual(a.detections, b.detections)
        self.assertEqual(a.source_event_id, data["event_id"])
        self.assertEqual(a.request_id, data["request_id"])
        self.assertEqual(a.occurred_at, "2026-09-07T01:00:00.000Z")
        self.assertEqual(len(a.detections), 2)
        self.assertEqual(next(d for d in a.detections if d["rule_id"] == "PHONE_NUMBER")["match_count"], 2)
        self.assertEqual(a.safe_metadata, {})
        self.assertTrue(all(d["evidence_fingerprint"] is None for d in a.detections))

    # 동일 원본 ID라도 서비스가 다르면 다른 사건 ID가 생성되는지 확인한다.
    def test_stable_id_source_namespace(self):
        data = sample()
        data["body"] = "password=synthetic-only"
        a = process_log(data).security_event.event_id
        data["service"] = "luck-nginx"
        self.assertNotEqual(a, process_log(data).security_event.event_id)

    # 본문뿐 아니라 전체 출력 JSON에서도 테스트 비밀번호 원문이 사라지는지 확인한다.
    def test_no_raw_secret_anywhere(self):
        data = sample()
        secret = "synthetic-UNIQUE-credential-123"
        data["attributes"] = {"items": [{"password": secret}], "note": f"api_key={secret}"}
        result = process_log(data)
        self.assertIsNone(result.failure)
        self.assertNotIn(secret, json.dumps(result.to_dict()))

    # 마스킹 오류를 강제로 발생시켜 부분 결과나 예외 속 원문이 출력되지 않는지 확인한다.
    def test_failed_mask_returns_no_partial_output(self):
        data = sample()
        data["body"] = "password=synthetic-only"
        with patch("app.engine.mask", side_effect=RuntimeError(data["body"])):
            result = process_log(data)
        self.assertIsNone(result.masked_log)
        self.assertIsNone(result.security_event)
        self.assertNotIn("synthetic-only", json.dumps(result.to_dict()))
        self.assertEqual(result.failure.error_code, "PROCESSING_ERROR")

    # 잘못된 버전·타입·시각·식별자·JSON 입력이 성공 결과로 나가지 않는지 확인한다.
    def test_invalid_inputs(self):
        for key, value in (("schema_version", "2.0"), ("body", None), ("attributes", []),
                           ("timestamp", "2026-09-07T10:00:00"), ("severity", "whatever"),
                           ("request_id", "tester@example.com"), ("body", "{"),
                           ("attributes", {"value": float("nan")})):
            with self.subTest(key=key, value=value):
                data = sample()
                data[key] = value
                result = process_log(data)
                self.assertIsNotNone(result.failure)
                self.assertIsNone(result.masked_log)

    # 계약에 없는 최상위 필드를 통한 민감정보 우회 유입을 거절하는지 확인한다.
    def test_reject_unknown_field(self):
        data = sample()
        data["password"] = "synthetic-only"
        self.assertEqual(process_log(data).failure.error_code, "INVALID_FIELDS")

    # 모델 객체를 직접 전달해도 입력 검증을 생략하지 않는지 확인한다.
    def test_dataclass_is_revalidated(self):
        data = sample()
        data["schema_version"] = "2.0"
        self.assertIsNotNone(process_log(NormalizedLog(**data)).failure)

    # 유니코드 이스케이프로 적힌 전화번호를 JSON 해석 후 탐지하는지 확인한다.
    def test_nested_json_escapes(self):
        data = sample()
        data["body"] = '{"message":"\\u0030\\u0031\\u0030-1234-5678"}'
        result = process_log(data)
        self.assertEqual(json.loads(result.masked_log.body_masked)["message"], "010-****-5678")

    # 문자열 내부 JSON의 중복 키도 실패 처리하는지 확인한다.
    def test_duplicate_embedded_json_rejected(self):
        data = sample()
        data["body"] = '{"password":"synthetic-only","password":"other"}'
        self.assertEqual(process_log(data).failure.error_code, "INVALID_EMBEDDED_JSON")

    # 너무 긴 본문이나 깊은 중첩 객체가 제한에 걸리는지 확인한다.
    def test_size_and_depth_limits(self):
        data = sample()
        data["body"] = "a" * 100001
        self.assertIsNotNone(process_log(data).failure)
        data = sample()
        value = {}
        for _ in range(15):
            value = {"child": value}
        data["attributes"] = value
        self.assertIsNotNone(process_log(data).failure)

    # 이미 가린 로그를 다시 처리해도 본문과 속성의 마스킹 결과가 유지되는지 확인한다.
    def test_masking_idempotence(self):
        data = sample()
        data["body"] = "tester@example.com 010-1234-5678 password=synthetic-only"
        data["attributes"] = {"name": "합성이름"}
        first = process_log(data).masked_log
        data["body"] = first.body_masked
        data["attributes"] = first.attributes
        second = process_log(data).masked_log
        self.assertEqual(second.body_masked, first.body_masked)
        self.assertEqual(second.attributes, first.attributes)

    # 키 없는 지문 생략, 서로 다른 키의 결과 차이 및 짧은 키 거절을 확인한다.
    def test_fingerprint_requires_secret(self):
        self.assertIsNone(fingerprint("value", None))
        self.assertNotEqual(fingerprint("value", b"a" * 32), fingerprint("value", b"b" * 32))
        data = sample()
        data["body"] = "password=synthetic-only"
        result = process_log(data, fingerprint_key=b"a" * 32)
        self.assertTrue(result.security_event.detections[0]["evidence_fingerprint"].startswith("hmac-sha256:"))
        self.assertIsNotNone(process_log(data, fingerprint_key=b"short").failure)

    # 두 탐지 구간이 겹칠 때 합집합 전체를 가려 끝부분이 남지 않는지 확인한다.
    def test_overlap_union_hides_suffix(self):
        a = Detection("A", "SECRET", "HIGH", 90, 1, 0, 5, "[REDACTED]")
        b = Detection("B", "PII", "MEDIUM", 50, 1, 3, 10, "partial")
        self.assertEqual(mask("0123456789 safe", [a, b]), "[REDACTED] safe")

    # 본문 범위를 벗어난 탐지 위치를 조용히 처리하지 않고 오류로 반환하는지 확인한다.
    def test_invalid_span(self):
        d = Detection("A", "SECRET", "HIGH", 90, 1, 0, 100, "x")
        with self.assertRaises(ValueError):
            mask("short", [d])


# 임시 파일로 실행기의 파일 경계와 실패 처리를 확인한다.
class CliTests(unittest.TestCase):
    # 잘못된 JSON·UTF-8 다음 줄도 처리하고 실패 파일에 원문이 남지 않는지 확인한다.
    def test_bad_lines_continue_without_payload_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.jsonl"
            bad = '{"password":"synthetic-secret",'
            source.write_bytes((json.dumps(sample()) + "\n" + bad + "\n").encode() + b"\xff\n" + (json.dumps(sample()) + "\n").encode())
            stats = run(source, root / "out")
            self.assertEqual(stats, {"read": 4, "masked": 2, "security_events": 0, "failed": 2})
            dlq = (root / "out/dead-letter.jsonl").read_text()
            self.assertNotIn("synthetic-secret", dlq)
            self.assertEqual([json.loads(line)["line_number"] for line in dlq.splitlines()], [2, 3])
            with self.assertRaises(FileExistsError):
                run(source, root / "out")

    # 크기 초과 행의 나머지를 소진한 뒤 다음 정상 행을 정확히 읽는지 확인한다.
    def test_oversize_line_is_drained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.jsonl"
            source.write_bytes(b"x" * 1_000_010 + b"\n" + (json.dumps(sample()) + "\n").encode())
            stats = run(source, root / "out")
            self.assertEqual(stats["failed"], 1)
            self.assertEqual(stats["masked"], 1)

    # 파일 입력 단계에서도 중복 JSON 키를 거절하는지 확인한다.
    def test_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.jsonl"
            source.write_text('{"body":"one","body":"two"}\n')
            self.assertEqual(run(source, root / "out")["failed"], 1)


if __name__ == "__main__":
    unittest.main()
