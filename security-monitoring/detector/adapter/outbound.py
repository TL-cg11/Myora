# 탐지 결과를 C가 소비하는 luck.* 계약 메시지로 바꾼다.
"""Convert detector output into the consumer-side Kafka contracts.

계약 원본은 ``luck-nginx/contracts``이며 사본이 ``contracts/consumer``에 있다.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from app.engine import POLICY_VERSION, VERSION
from app.hashing import stable_id
from app.models import Detection, MaskedLog, ProcessingFailure, SecurityEvent
from adapter.policy import MaskingPolicy

CONTRACT_VERSION = "1.0"
MAX_MASKED_MESSAGE = 65535
MAX_MASKED_EXCERPT = 1000
MAX_MATCH_COUNT = 65535
TRUNCATION_MARK = "...[TRUNCATED]"


# sha256:/hmac-sha256: 접두사를 떼어 C 계약의 hex 64자리 형식에 맞춘다.
def _hex_digest(value: str | None) -> str | None:
    if not value:
        return None
    digest = value.rsplit(":", 1)[-1]
    return digest if len(digest) == 64 else None


# 계약 최대 길이를 넘는 문자열은 잘렸다는 표시를 남기고 자른다.
def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARK)] + TRUNCATION_MARK


# 점수 구간을 위험등급으로 바꾼다. app.risk와 같은 기준을 사용한다.
def _level(score: int) -> str:
    return "CRITICAL" if score >= 95 else "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"


# 정책 버전을 결과 메시지 한 필드로 합친다. 계약 최대 길이는 32자다.
def masking_policy_version(policy: MaskingPolicy) -> str:
    return f"was-{policy.policy_version}+det-{POLICY_VERSION}"[:32]


# 같은 규칙의 여러 탐지를 하나로 묶어 C의 detection 항목을 만든다.
def build_detection_entries(event_id: str, detections: Iterable[Detection]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        grouped.setdefault(detection.rule_id, []).append(detection)
    entries = []
    for rule_id, matches in sorted(grouped.items()):
        sample = matches[0]
        entries.append(
            {
                "detection_id": stable_id(event_id, rule_id, sample.rule_version),
                "rule_id": rule_id,
                "rule_version": sample.rule_version,
                "category": sample.category,
                "entity_type": rule_id,
                "risk_level": sample.risk_level,
                "confidence": max(match.confidence for match in matches),
                "match_count": min(len(matches), MAX_MATCH_COUNT),
                "evidence_fingerprint": None,
                "locations": [
                    {"field": match.field, "start": match.start, "end": match.end}
                    for match in matches
                ],
            }
        )
    return entries


# 엔진 detection dict를 C 계약 필드 이름으로 바꾼다.
def _contract_detection(detection: dict[str, Any]) -> dict[str, Any]:
    locations = detection.get("locations")
    return {
        "detection_id": detection["detection_id"],
        "rule_id": detection["rule_id"],
        "rule_version": detection["rule_version"],
        "category": detection["category"],
        "entity_type": detection["entity_type"][:64],
        "risk_level": detection["risk_level"],
        "confidence": detection["confidence"],
        "match_count": min(detection["match_count"], MAX_MATCH_COUNT),
        "evidence_fingerprint": _hex_digest(detection.get("evidence_fingerprint")),
        "locations_json": locations if locations else None,
    }


# Loki로 보낼 마스킹 로그 메시지. 마스킹된 속성은 safe_metadata에 넣는다.
def masked_log_message(
    masked: MaskedLog,
    *,
    policy: MaskingPolicy,
    source_kind: str,
    risk_level: str,
    risk_score: int,
    detected_rules: list[str],
) -> dict[str, Any]:
    return {
        "event_id": masked.event_id,
        "schema_version": CONTRACT_VERSION,
        "request_id": masked.request_id,
        "occurred_at": masked.timestamp,
        "environment": masked.environment,
        "source_service": masked.service,
        "source_type": masked.source_type,
        "masking_policy_version": masking_policy_version(policy),
        "masked_message": _clip(masked.body_masked, MAX_MASKED_MESSAGE),
        "body_hash": _hex_digest(masked.body_hash),
        "safe_metadata": {
            "source_kind": source_kind,
            "severity": masked.severity,
            "event_name": masked.event_name,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "detected_rules": detected_rules,
            "detector_version": masked.detector_version,
            "attributes": masked.attributes,
        },
    }


# 엔진과 같은 규칙으로 보안 이벤트 ID를 만든다. 같은 입력은 항상 같은 ID가 된다.
def security_event_id(masked: MaskedLog) -> str:
    return stable_id(masked.environment, masked.service, masked.event_id, VERSION, POLICY_VERSION)


# MariaDB에 저장할 보안 이벤트 메시지. 원본 본문은 넣지 않는다.
def security_event_message(
    masked: MaskedLog,
    event: SecurityEvent | None,
    extra: list[dict[str, Any]],
    *,
    policy: MaskingPolicy,
    source_kind: str,
    risk_level: str,
    risk_score: int,
    detected_at: datetime | None = None,
) -> dict[str, Any]:
    detections = list(event.detections) if event is not None else []
    detections.extend(extra)
    clock = detected_at or datetime.now(timezone.utc)
    stamp = clock.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "event_id": event.event_id if event is not None else security_event_id(masked),
        "source_event_id": masked.event_id,
        "schema_version": CONTRACT_VERSION,
        "request_id": masked.request_id,
        "occurred_at": event.occurred_at if event is not None else masked.timestamp,
        "detected_at": event.detected_at if event is not None else stamp,
        "environment": masked.environment,
        "source_service": masked.service,
        "source_type": masked.source_type,
        "event_name": masked.event_name,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "detector_version": masked.detector_version[:32],
        "masking_policy_version": masking_policy_version(policy),
        "masked_excerpt": _clip(masked.body_masked, MAX_MASKED_EXCERPT) or None,
        "body_hash": _hex_digest(masked.body_hash),
        "safe_metadata": {"source_kind": source_kind, "severity": masked.severity},
        "detections": [_contract_detection(item) for item in detections],
    }


# 처리 실패를 원문 없이 알린다. 재처리 도구는 topic/partition/offset으로 원본을 찾는다.
def dead_letter_message(
    failure: ProcessingFailure,
    *,
    topic: str,
    partition: int,
    offset: int,
    consumer_group: str,
    message_key: str | None,
    payload_hash: str,
    failed_at: datetime | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    clock = failed_at or datetime.now(timezone.utc)
    payload = asdict(failure)
    payload.update(
        {
            "source_topic": topic,
            "partition": partition,
            "offset": offset,
            "consumer_group": consumer_group,
            "message_key": message_key,
            "payload_hash": payload_hash,
            "failed_at": clock.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "retry_count": retry_count,
        }
    )
    return payload


# 엔진 결과와 어댑터 추가 탐지를 합쳐 최종 위험등급과 규칙 목록을 계산한다.
def merge_risk(
    masked: MaskedLog, extra: Iterable[Detection]
) -> tuple[str, int, list[str]]:
    extra = list(extra)
    score = max([masked.risk_score, *(item.risk_score for item in extra)])
    rules = sorted({*masked.detected_rules, *(item.rule_id for item in extra)})
    return _level(score), score, rules
