# A 입력과 B 출력의 자료형을 정의한다. 실제 DB 저장 및 Kafka 통신은 담당하지 않는다.
"""Transport-neutral v1 models. No database or broker dependency."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import math
from typing import Any


# 외부로 전달해도 원문이 노출되지 않는 고정 오류 코드용 예외.
class InputError(ValueError):
    """Only fixed, non-payload error codes may cross the processing boundary."""


# 필수 문자열의 빈 값·최대 길이를 검사하고, nullable인 경우에만 None을 허용한다.
def bounded_string(value: Any, maximum: int, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, str) and 0 < len(value) <= maximum
    )


@dataclass(frozen=True)
# A가 전달하는 정규화 로그. frozen은 필드 재할당을 막지만 내부 dict까지 불변은 아니다.
class NormalizedLog:
    schema_version: str  # 입출력 계약 버전
    event_id: str  # 해당 로그 또는 보안 이벤트의 고유 ID
    request_id: str | None  # 서비스 간 요청 추적 ID; 없으면 None
    timestamp: str  # 시간대가 포함된 원본 로그 시각
    environment: str  # 실행 환경(test/development/production 등)
    service: str  # 원본 로그 생성 서비스
    source_type: str  # 로그 종류(llm_prompt 등)
    event_name: str | None  # 발생한 작업 이름; 없으면 None
    severity: str  # 원본 운영 로그 수준; 보안 위험등급과 구분
    body: str  # 검사할 원본 문자열; 출력에 그대로 복사하지 않음
    attributes: dict = field(default_factory=dict)  # 추가 구조화 데이터; 출력 모델에서는 마스킹 완료 값

    @classmethod
    # 외부 입력을 검사한 후 모델을 만든다. 잘못된 값은 원문 없는 고정 오류 코드로 거절한다.
    def from_dict(cls, data: dict) -> "NormalizedLog":
        if not isinstance(data, dict):
            raise InputError("INVALID_OBJECT")
        # 확장 필드를 임의로 통과시키면 검사되지 않은 값이 새어 나갈 수 있어 정확히 일치시킨다.
        required = set(cls.__dataclass_fields__)
        if set(data) != required:
            raise InputError("INVALID_FIELDS")
        if data["schema_version"] != "1.0":
            raise InputError("UNSUPPORTED_SCHEMA")
        limits = {"event_id": 64, "request_id": 64, "environment": 32,
                  "service": 64, "source_type": 64, "event_name": 128,
                  "severity": 16, "timestamp": 40}
        for key, size in limits.items():
            if not bounded_string(data[key], size, key in {"request_id", "event_name"}):
                raise InputError("INVALID_FIELD_TYPE")
        try:
            timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise InputError("INVALID_TIMESTAMP") from None
        if data["severity"] not in {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"}:
            raise InputError("INVALID_SEVERITY")
        if not isinstance(data["body"], str) or len(data["body"]) > 100_000:
            raise InputError("INVALID_BODY")
        if not isinstance(data["attributes"], dict):
            raise InputError("INVALID_ATTRIBUTES")
        # 재귀 호출 전체에서 누적 방문 수를 공유해 폭이 넓은 입력도 제한한다.
        count = [0]

        # 중첩 객체의 깊이·원소 수·자료형을 검사해 과도한 입력과 비표준 숫자를 막는다.
        def validate(value: Any, depth: int = 0) -> None:
            count[0] += 1
            if depth > 12 or count[0] > 5000:
                raise InputError("INPUT_LIMIT")
            if isinstance(value, dict):
                for k, v in value.items():
                    if not isinstance(k, str) or len(k) > 256:
                        raise InputError("INVALID_ATTRIBUTES")
                    validate(v, depth + 1)
            elif isinstance(value, list):
                for v in value:
                    validate(v, depth + 1)
            elif isinstance(value, str):
                if len(value) > 100_000:
                    raise InputError("INPUT_LIMIT")
            elif value is not None and type(value) not in {bool, int, float}:
                raise InputError("INVALID_ATTRIBUTES")
            elif isinstance(value, float) and not math.isfinite(value):
                raise InputError("INVALID_ATTRIBUTES")

        validate(data["attributes"])
        return cls(**data)


@dataclass(frozen=True)
# 문자열 한 구간의 내부 탐지 결과. 원본 민감 값 자체를 필드에 저장하지 않는다.
class Detection:
    rule_id: str  # 탐지 규칙 식별자
    category: str  # PII/SECRET 등 탐지 분류
    risk_level: str  # 보안 위험등급
    risk_score: int  # 정책에서 정한 0~100 위험 점수
    confidence: float  # 규칙 신뢰도 초기값; 보정된 확률은 아님
    start: int  # 탐지 시작 문자 위치(포함)
    end: int  # 탐지 종료 문자 위치(제외)
    replacement: str  # 탐지 구간을 대체할 마스킹 문구
    field: str = "/body"  # 탐지 위치를 나타내는 안전한 경로
    rule_version: str = "1.0"  # 탐지 규칙 버전


@dataclass(frozen=True)
# Loki로 보낼 마스킹 로그. 정상 입력마다 한 건을 생성한다.
class MaskedLog:
    schema_version: str  # 입출력 계약 버전
    event_id: str  # 해당 로그 또는 보안 이벤트의 고유 ID
    request_id: str | None  # 서비스 간 요청 추적 ID; 없으면 None
    timestamp: str  # 시간대가 포함된 원본 로그 시각
    environment: str  # 실행 환경(test/development/production 등)
    service: str  # 원본 로그 생성 서비스
    source_type: str  # 로그 종류(llm_prompt 등)
    event_name: str | None  # 발생한 작업 이름; 없으면 None
    severity: str  # 원본 운영 로그 수준; 보안 위험등급과 구분
    body_masked: str  # 민감정보를 가린 본문
    attributes: dict  # 추가 구조화 데이터; 출력 모델에서는 마스킹 완료 값
    body_hash: str  # 원본 본문의 SHA-256 지문
    detected_rules: list[str]  # 해당 로그에서 탐지한 규칙 목록
    risk_level: str  # 보안 위험등급
    risk_score: int  # 정책에서 정한 0~100 위험 점수
    detector_version: str  # 탐지 프로그램 버전
    masking_policy_version: str  # 마스킹 정책 버전


@dataclass(frozen=True)
# C의 사건/탐지 테이블에 매핑할 이벤트. 동일 규칙은 detections에서 묶는다.
class SecurityEvent:
    schema_version: str  # 입출력 계약 버전
    event_id: str  # 해당 로그 또는 보안 이벤트의 고유 ID
    source_event_id: str  # A가 생성한 원본 로그 ID
    request_id: str | None  # 서비스 간 요청 추적 ID; 없으면 None
    occurred_at: str  # 원본 로그 발생 시각(UTC)
    detected_at: str  # 탐지 시각(UTC)
    environment: str  # 실행 환경(test/development/production 등)
    source_service: str  # 원본 로그 생성 서비스; C 저장용 필드명
    source_type: str  # 로그 종류(llm_prompt 등)
    event_name: str | None  # 발생한 작업 이름; 없으면 None
    risk_level: str  # 보안 위험등급
    risk_score: int  # 정책에서 정한 0~100 위험 점수
    detector_version: str  # 탐지 프로그램 버전
    masking_policy_version: str  # 마스킹 정책 버전
    masked_excerpt: str  # C DB에 저장할 마스킹 발췌문(최대 1,000자)
    body_hash: str  # 원본 본문의 SHA-256 지문
    detections: list[dict]  # 규칙별로 묶은 개별 탐지 결과
    safe_metadata: dict  # 추가 허용 메타데이터; 현재는 빈 객체


@dataclass(frozen=True)
# 실패 경로의 출력 모델. 원본 payload나 예외 전문은 포함하지 않는다.
class ProcessingFailure:
    schema_version: str  # 입출력 계약 버전
    error_code: str  # 원문을 포함하지 않는 고정 오류 코드
    failure_stage: str  # 실패한 처리 단계
    retryable: bool  # 원인 해결 후 재시도할 수 있는 오류인지 표시
    detector_version: str = "1.1.0"  # 탐지 프로그램 버전


@dataclass(frozen=True)
# 성공 결과 또는 실패 정보 중 한쪽을 반환하는 컨테이너.
class ProcessingResult:
    masked_log: MaskedLog | None = None  # 성공 시 마스킹 로그; 실패 시 None
    security_event: SecurityEvent | None = None  # 탐지가 있는 성공 로그에만 생성
    failure: ProcessingFailure | None = None  # 실패 정보; 성공 시 None

    # 중첩 dataclass를 JSON 직렬화 가능한 dict로 변환한다.
    def to_dict(self) -> dict:
        return asdict(self)
