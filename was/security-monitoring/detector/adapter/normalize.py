# 원본 Kafka 로그를 탐지 엔진의 NormalizedLog 입력으로 바꾼다.
"""Map WAS and Nginx Kafka records onto the detector's NormalizedLog input."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from adapter.policy import MaskingPolicy, mask_ip, pseudonymize

# 탐지 엔진이 identity 필드에서 허용하는 문자 집합.
UNSAFE_IDENTITY = re.compile(r"[^A-Za-z0-9_.:/-]")
LEADING_UNSAFE = re.compile(r"^[^A-Za-z0-9]+")
# 탐지 엔진이 허용하는 severity 값.
ALLOWED_SEVERITY = {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"}
# C 계약의 environment enum과 흔히 쓰는 별칭.
ENVIRONMENT_ALIASES = {
    "dev": "development", "develop": "development", "development": "development",
    "local": "development", "test": "test", "testing": "test", "qa": "test",
    "stage": "staging", "staging": "staging",
    "prod": "production", "production": "production", "live": "production",
}
# NormalizedLog 상위 필드로 올라가므로 attributes에 중복해서 넣지 않는다.
WAS_CONSUMED_FIELDS = {
    "schema_version", "event_id", "request_id", "timestamp",
    "environment", "severity", "service", "event_type",
}
NGINX_CONSUMED_FIELDS = {
    "schema_version", "event_id", "request_id", "timestamp", "time",
    "environment", "severity", "service", "source_type", "event_name",
}


class AdapterError(ValueError):
    """원문을 포함하지 않는 고정 오류 코드로 메시지를 거절한다."""

    def __init__(self, code: str, stage: str = "VALIDATE", retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.retryable = retryable


@dataclass(frozen=True)
# 엔진에 넘길 입력과 어댑터가 추가로 알아야 할 정보를 함께 담는다.
class NormalizedInput:
    log: dict[str, Any]  # process_log에 그대로 넘길 NormalizedLog dict
    source_kind: str  # was 또는 nginx
    prompt_injection: bool  # 본문에 Prompt Injection 탐지를 적용할지 여부
    dropped_fields: tuple[str, ...] = ()  # 정책이 drop으로 지정해 제외한 필드


# identity 필드는 허용 문자만 남긴다. 비면 사용할 수 없는 값으로 본다.
def safe_identity(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = LEADING_UNSAFE.sub("", UNSAFE_IDENTITY.sub("-", str(value)).strip())[:limit]
    return text or None


# 별칭을 C 계약의 enum 값으로 맞춘다. 알 수 없으면 메시지를 거절한다.
def normalize_environment(value: Any, default: str) -> str:
    text = str(value).strip().lower() if value not in (None, "") else default
    resolved = ENVIRONMENT_ALIASES.get(text)
    if resolved is None:
        raise AdapterError("UNSUPPORTED_ENVIRONMENT")
    return resolved


# 시간대가 있는 시각을 UTC ISO 8601(Z)로 통일한다.
def to_utc_z(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            raise AdapterError("INVALID_TIMESTAMP") from None
        # 시간대가 없으면 UTC로 읽는다. Fluent Bit 기본 출력이 여기에 해당한다.
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    else:
        raise AdapterError("INVALID_TIMESTAMP")
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# 탐지 엔진이 아는 값으로 맞춘다. 알 수 없는 값은 INFO로 낮춘다.
def _severity(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in ALLOWED_SEVERITY else "INFO"


# HTTP 상태 코드로 로그 수준을 정한다.
def _severity_from_status(status: Any) -> str:
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "INFO"
    return "ERROR" if code >= 500 else "WARNING" if code >= 400 else "INFO"


# 정책이 정한 처리 방식대로 필드 값 하나를 바꾼다.
def _apply_action(action: str, field: str, value: Any, key: bytes) -> Any:
    if action == "pass":
        return value
    if action == "pseudonymize":
        return None if value in (None, "") else pseudonymize(value, key, field.replace(".", "_"))
    if action == "mask_ip":
        return None if value is None else mask_ip(value)
    if action == "reject":
        raise AdapterError("UNKNOWN_INPUT_FIELD")
    raise AdapterError("UNSUPPORTED_POLICY_ACTION")


# 정책을 한 매핑에 적용해 자유 텍스트, 마스킹된 속성, 제외 필드를 나눈다.
def _apply_policy(
    values: dict[str, Any], policy: MaskingPolicy, key: bytes, prefix: str = ""
) -> tuple[dict[str, Any], list[str], list[str], bool]:
    attributes: dict[str, Any] = {}
    free_text: list[str] = []
    dropped: list[str] = []
    injection = False
    for name, value in values.items():
        field = prefix + name
        action = policy.action_for(field)
        if action == "drop":
            dropped.append(field)
            continue
        if action == "detect_and_mask":
            # 자유 텍스트는 본문으로 올려 탐지 엔진이 내용 기반으로 마스킹한다.
            if isinstance(value, str) and value:
                free_text.append(value)
                injection = injection or policy.prompt_injection_enabled(field)
            continue
        attributes[name] = _apply_action(action, field, value, key)
    return attributes, free_text, dropped, injection


# WAS JSON 로그(myohan.was.app)를 정책에 따라 정규화한다.
def normalize_was_log(
    event: Any, policy: MaskingPolicy, *, pseudonym_key: bytes, default_environment: str
) -> NormalizedInput:
    if not isinstance(event, dict):
        raise AdapterError("INVALID_OBJECT")
    if str(event.get("schema_version")) != policy.schema_version:
        raise AdapterError("UNSUPPORTED_SCHEMA")
    event_id = safe_identity(event.get("event_id"), 64)
    if event_id is None:
        raise AdapterError("MISSING_EVENT_ID")

    raw_input = event.get("input") or {}
    if not isinstance(raw_input, dict):
        raise AdapterError("INVALID_INPUT_OBJECT")
    raw_output = event.get("output") or {}
    if not isinstance(raw_output, dict):
        raise AdapterError("INVALID_OUTPUT_OBJECT")
    skipped = WAS_CONSUMED_FIELDS | {"input", "output"}
    payload = {name: value for name, value in event.items() if name not in skipped}
    attributes, free_text, dropped, injection = _apply_policy(payload, policy, pseudonym_key)
    input_attributes, input_text, input_dropped, input_injection = _apply_policy(
        raw_input, policy, pseudonym_key, prefix="input."
    )
    if input_attributes:
        attributes["input"] = input_attributes
    output_attributes, output_text, output_dropped, _ = _apply_policy(
        raw_output, policy, pseudonym_key, prefix="output."
    )
    if output_attributes:
        attributes["output"] = output_attributes

    event_type = str(event.get("event_type") or "log")
    feature = str(event.get("feature") or "unknown")
    log = {
        "schema_version": "1.0",
        "event_id": event_id,
        "request_id": safe_identity(event.get("request_id"), 64),
        "timestamp": to_utc_z(event.get("timestamp")),
        "environment": normalize_environment(event.get("environment"), default_environment),
        "service": safe_identity(event.get("service"), 64) or "luck-was",
        "source_type": safe_identity(event_type, 64) or "log",
        "event_name": safe_identity(feature + "." + event_type, 128),
        "severity": _severity(event.get("severity")),
        "body": "\n".join(free_text + input_text + output_text),
        "attributes": attributes,
    }
    return NormalizedInput(
        log=log,
        source_kind="was",
        prompt_injection=injection or input_injection,
        dropped_fields=tuple(dropped + input_dropped + output_dropped),
    )


# Loki에 남길 요청 한 줄을 만든다. 질의 문자열까지 포함해 본문 검사 대상으로 삼는다.
def _request_line(record: dict[str, Any]) -> str:
    line = record.get("request")
    if isinstance(line, str) and line:
        return line
    parts = [record.get("method"), record.get("uri")]
    return " ".join(str(part) for part in parts if isinstance(part, str) and part)


# Nginx access 로그(myohan.nginx.access)를 정규화한다.
# 전용 정책 파일이 없어 WAS 정책의 필드 규칙을 이름이 같은 필드에 그대로 적용한다.
def normalize_nginx_log(
    record: Any,
    policy: MaskingPolicy,
    *,
    pseudonym_key: bytes,
    default_environment: str,
    fallback_event_id: str,
) -> NormalizedInput:
    if not isinstance(record, dict):
        raise AdapterError("INVALID_OBJECT")
    payload = {name: value for name, value in record.items() if name not in NGINX_CONSUMED_FIELDS}
    # 질의 문자열에 개인정보가 실릴 수 있다. 속성에는 경로만 남기고 검사는 본문에서 한다.
    if isinstance(payload.get("uri"), str):
        payload["uri"] = payload["uri"].partition("?")[0]
    attributes, free_text, dropped, _ = _apply_policy(payload, policy, pseudonym_key)

    body_parts = [_request_line(record)] if _request_line(record) else []
    log = {
        "schema_version": "1.0",
        "event_id": safe_identity(record.get("event_id"), 64) or fallback_event_id,
        "request_id": safe_identity(record.get("request_id"), 64),
        "timestamp": to_utc_z(record.get("timestamp") or record.get("time")),
        "environment": normalize_environment(record.get("environment"), default_environment),
        "service": safe_identity(record.get("service"), 64) or "luck-nginx",
        "source_type": safe_identity(record.get("source_type"), 64) or "nginx_access",
        "event_name": safe_identity(record.get("event_name"), 128) or "nginx.access",
        "severity": _severity(record.get("severity"))
        if record.get("severity")
        else _severity_from_status(record.get("status")),
        "body": "\n".join(free_text + body_parts),
        "attributes": attributes,
    }
    return NormalizedInput(
        log=log, source_kind="nginx", prompt_injection=False, dropped_fields=tuple(dropped)
    )
