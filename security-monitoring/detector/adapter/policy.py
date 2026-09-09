# 마스킹 정책 로더: schemas/was-log-masking-policy-v1.json의 필드 규칙을 그대로 따른다.
"""Field-level masking policy shared with the WAS log schema."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
from typing import Any

# adapter/ → detector/ → security-monitoring/ → luck-was/
POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "was-log-masking-policy-v1.json"
)
# 정책 파일에서 허용하는 필드 처리 방식.
SUPPORTED_ACTIONS = {"pseudonymize", "mask_ip", "detect_and_mask", "pass", "drop"}
SUPPORTED_DEFAULT_ACTIONS = {"reject", "pass", "drop"}
IP_REDACTION = "[REDACTED_IP]"


class PolicyError(RuntimeError):
    """정책 파일을 읽을 수 없거나 알 수 없는 처리 방식이 들어 있는 상태."""


@dataclass(frozen=True)
# 정책 파일 한 개를 표현한다. 실행 중에는 변경하지 않는다.
class MaskingPolicy:
    policy_version: str  # 정책 버전. 결과 메시지의 masking_policy_version에 넣는다
    schema_version: str  # 이 정책이 다루는 로그 스키마 버전
    fields: dict[str, dict[str, Any]]  # 필드 경로 → 처리 규칙
    unknown_input_field_action: str  # 정책에 없는 input 하위 필드 처리 방식
    other_schema_field_action: str  # 정책에 없는 그 외 스키마 필드 처리 방식

    # 정책에 정의된 필드면 그 처리 방식을, 아니면 기본 정책을 돌려준다.
    def action_for(self, field: str) -> str:
        rule = self.fields.get(field)
        if rule is not None:
            return rule["action"]
        if field.startswith("input."):
            return self.unknown_input_field_action
        return self.other_schema_field_action

    # 자유 텍스트에서 Prompt Injection까지 확인할 필드인지 알려준다.
    def prompt_injection_enabled(self, field: str) -> bool:
        return bool(self.fields.get(field, {}).get("prompt_injection_detection"))

    # detect_and_mask 대상 필드 목록. 본문으로 올릴 자유 텍스트를 고를 때 사용한다.
    def free_text_fields(self) -> tuple[str, ...]:
        return tuple(
            field
            for field, rule in self.fields.items()
            if rule["action"] == "detect_and_mask"
        )


# 정책 파일을 검증하며 읽는다. 알 수 없는 action이면 실행 전에 실패시킨다.
def load_policy(path: Path | str | None = None) -> MaskingPolicy:
    location = Path(path or os.environ.get("WAS_MASKING_POLICY_PATH") or POLICY_PATH)
    try:
        document = json.loads(location.read_text(encoding="utf-8"))
    except OSError as error:
        raise PolicyError(f"마스킹 정책 파일을 읽을 수 없습니다: {location}") from error
    except ValueError as error:
        raise PolicyError(f"마스킹 정책 파일이 올바른 JSON이 아닙니다: {location}") from error
    if not isinstance(document, dict):
        raise PolicyError("마스킹 정책은 JSON 객체여야 합니다.")

    fields = document.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise PolicyError("마스킹 정책에 fields가 없습니다.")
    for field, rule in fields.items():
        if not isinstance(rule, dict) or rule.get("action") not in SUPPORTED_ACTIONS:
            raise PolicyError(f"지원하지 않는 마스킹 처리 방식입니다: {field}")

    defaults = document.get("default") or {}
    unknown_input = defaults.get("unknown_input_field_action", "reject")
    other_field = defaults.get("other_schema_field_action", "pass")
    for action in (unknown_input, other_field):
        if action not in SUPPORTED_DEFAULT_ACTIONS:
            raise PolicyError(f"지원하지 않는 기본 처리 방식입니다: {action}")

    return MaskingPolicy(
        policy_version=str(document.get("policy_version", "0")),
        schema_version=str(document.get("schema_version", "1.0")),
        fields=fields,
        unknown_input_field_action=unknown_input,
        other_schema_field_action=other_field,
    )


# 같은 사용자를 항상 같은 토큰으로 바꾼다. 키가 없으면 원본을 되찾기 쉬워 키를 요구한다.
def pseudonymize(value: Any, key: bytes, label: str) -> str:
    if not key:
        raise PolicyError("가명화 키가 없습니다.")
    material = f"{label}:{value}".encode("utf-8")
    digest = hmac.new(key, material, hashlib.sha256).hexdigest()
    return f"{label}_{digest[:24]}"


# IPv4는 마지막 옥텟, IPv6는 하위 주소를 지워 대역만 남긴다.
def mask_ip(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return IP_REDACTION
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return IP_REDACTION
    if address.version == 4:
        return str(ipaddress.ip_network(f"{address}/24", strict=False).network_address)
    return str(ipaddress.ip_network(f"{address}/48", strict=False).network_address)
