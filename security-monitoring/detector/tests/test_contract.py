# B 입출력이 C에게 전달할 JSON 계약과 일치하는지 검사하는 테스트.
"""Dependency-free checks for the subset used by the checked-in JSON schemas.

This is a test helper, not a general-purpose JSON Schema validator.
Unknown keywords fail the test rather than being silently ignored.
"""
from datetime import datetime
import json
from pathlib import Path
import unittest

from app.engine import process_log

ROOT = Path(__file__).resolve().parents[1]


# 이 프로젝트에서 사용하는 스키마 키워드만 재귀 검증하는 테스트 전용 도우미다.
def check(value, schema):
    # $comment는 설명 전용 키워드라 허용하되 데이터 검증 조건으로 사용하지 않는다.
    supported = {"$schema", "title", "type", "properties", "additionalProperties", "required",
                 "anyOf", "const", "enum", "maxLength", "format", "items", "minItems",
                 "uniqueItems", "minimum", "maximum", "$comment"}
    assert not set(schema) - supported
    if "anyOf" in schema:
        successes = []
        for option in schema["anyOf"]:
            try:
                check(value, option)
            except (AssertionError, ValueError, TypeError):
                continue
            successes.append(True)
        assert successes
        return
    if "const" in schema:
        assert value == schema["const"]
    if "enum" in schema:
        assert value in schema["enum"]
    expected = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "boolean": bool, "null": type(None)}
    if expected:
        assert isinstance(value, types[expected])
        if expected in {"integer", "number"}:
            assert not isinstance(value, bool)
    if "maxLength" in schema:
        assert len(value) <= schema["maxLength"]
    if "minimum" in schema:
        assert value >= schema["minimum"]
    if "maximum" in schema:
        assert value <= schema["maximum"]
    if "format" in schema:
        assert schema["format"] == "date-time"
        assert datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    if expected == "object":
        properties = schema.get("properties", {})
        assert set(schema.get("required", [])) <= set(value)
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(properties)
        for key in set(properties) & set(value):
            check(value[key], properties[key])
    if expected == "array":
        assert len(value) >= schema.get("minItems", 0)
        if schema.get("uniqueItems"):
            assert len(value) == len({json.dumps(v, sort_keys=True) for v in value})
        for item in value:
            check(item, schema["items"])


# C와 공유하는 입력·출력 필드 계약 테스트.
class ContractTests(unittest.TestCase):
    # fixture 입력과 실제 성공·실패 출력이 각 JSON Schema와 맞는지 확인한다.
    def test_fixtures_and_outputs_match_contracts(self):
        schemas = {name: json.loads((ROOT / f"contracts/v1/{name}.schema.json").read_text(encoding="utf-8"))
                   for name in ("normalized-log", "masked-log", "security-event", "dead-letter")}
        cases = json.loads((ROOT / "tests/fixtures/cases.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(name=case["name"]):
                check(case["input"], schemas["normalized-log"])
                output = process_log(case["input"]).to_dict()
                check(output["masked_log"], schemas["masked-log"])
                if output["security_event"]:
                    check(output["security_event"], schemas["security-event"])
        check(process_log({}).to_dict()["failure"], schemas["dead-letter"])

    # 원문 필드 추가나 DB 제한을 넘는 발췌문이 계약 검사에서 거절되는지 확인한다.
    def test_contract_rejects_raw_extra_field_and_overlong_excerpt(self):
        # 한국어 설명이 포함된 스키마는 Windows 기본 인코딩 대신 UTF-8로 읽는다.
        schema = json.loads((ROOT / "contracts/v1/security-event.schema.json").read_text(encoding="utf-8"))
        cases = json.loads((ROOT / "tests/fixtures/cases.json").read_text(encoding="utf-8"))["cases"]
        event = process_log(cases[6]["input"]).to_dict()["security_event"]
        event["body"] = "raw-content"
        with self.assertRaises(AssertionError):
            check(event, schema)
        del event["body"]
        event["masked_excerpt"] = "a" * 1001
        with self.assertRaises(AssertionError):
            check(event, schema)


if __name__ == "__main__":
    unittest.main()
