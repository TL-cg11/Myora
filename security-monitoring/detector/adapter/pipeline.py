# Kafka 한 메시지를 결과 메시지 목록으로 바꾸는 순수 처리 경로. broker에 의존하지 않는다.
"""Broker-independent transformation of one raw record into contract messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any

from app import jsonio
from app.engine import process_log
from app.hashing import stable_id
from app.models import ProcessingFailure
from app.rules.ner import NERRecognizer, TransformersNERRecognizer
from app.rules.pii_context import (PIICandidateVerifier,
                                   TransformersPIICandidateVerifier)
from adapter import outbound, prompt_injection
from adapter.config import Settings
from adapter.normalize import AdapterError, normalize_nginx_log, normalize_was_log
from adapter.policy import MaskingPolicy
from adapter.safety import contains_sensitive

# broker가 허용하더라도 탐지 엔진의 입력 상한을 넘는 메시지는 받지 않는다.
MAX_MESSAGE_BYTES = 1_000_000


@dataclass(frozen=True)
# 발행할 메시지 한 건. 직렬화와 전송은 runner가 맡는다.
class OutboundMessage:
    topic: str  # 발행 대상 topic
    key: str | None  # 같은 요청을 같은 partition으로 보내는 message key
    value: dict[str, Any]  # 계약을 만족하는 JSON 본문


@dataclass(frozen=True)
# 메시지 한 건의 처리 결과. 실패해도 원문은 담지 않는다.
class PipelineResult:
    messages: tuple[OutboundMessage, ...]  # 발행할 메시지
    failed: bool  # dead-letter로 처리했는지 여부
    error_code: str | None = None  # 실패 시 고정 오류 코드
    source_kind: str | None = None  # was 또는 nginx
    risk_level: str | None = None  # 성공 시 최종 위험등급


# 원본 바이트의 SHA-256. 원문을 복사하지 않고 같은 메시지를 비교할 때 쓴다.
def payload_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class MaskingPipeline:
    """원본 로그 → 정책 적용 → 탐지·마스킹 → 결과 계약 메시지."""

    def __init__(self, settings: Settings, policy: MaskingPolicy,
                 *, ner_recognizer: NERRecognizer | None = None,
                 pii_verifier: PIICandidateVerifier | None = None) -> None:
        self._settings = settings
        self._policy = policy
        self._ner_recognizer = ner_recognizer
        if self._ner_recognizer is None and settings.ner_enabled:
            self._ner_recognizer = TransformersNERRecognizer(
                settings.ner_model,
                threshold=settings.ner_threshold,
                local_files_only=settings.ner_local_files_only,
            )
        self._pii_verifier = pii_verifier
        if self._pii_verifier is None and settings.pii_context_enabled:
            self._pii_verifier = TransformersPIICandidateVerifier(
                settings.pii_context_model,
                non_pii_threshold=settings.pii_context_non_pii_threshold,
                local_files_only=settings.pii_context_local_files_only,
            )

    # 한 메시지를 처리한다. 어느 단계에서 실패해도 부분 결과를 발행하지 않는다.
    def handle(
        self,
        raw: bytes,
        *,
        topic: str,
        partition: int,
        offset: int,
        message_key: str | None = None,
        detected_at: datetime | None = None,
    ) -> PipelineResult:
        digest = payload_hash(raw)
        stage = "DECODE"
        try:
            if len(raw) > MAX_MESSAGE_BYTES:
                raise AdapterError("MESSAGE_TOO_LARGE", "DECODE")
            try:
                record = jsonio.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError, RecursionError):
                raise AdapterError("INVALID_JSON", "DECODE") from None

            stage = "VALIDATE"
            normalized = self._normalize(record, topic, digest)

            result = process_log(
                normalized.log,
                fingerprint_key=self._settings.fingerprint_key,
                ner_recognizer=self._ner_recognizer,
                pii_verifier=self._pii_verifier,
            )
            if result.failure is not None:
                return self._dead_letter(
                    result.failure, topic, partition, offset, message_key, digest
                )

            stage = "BUILD_EVENT"
            return self._success(normalized, result, detected_at)
        except AdapterError as error:
            failure = ProcessingFailure("1.0", error.code, error.stage, error.retryable)
            return self._dead_letter(failure, topic, partition, offset, message_key, digest)
        except Exception:
            # 예외 문자열에는 원문이 들어갈 수 있어 고정 코드만 남긴다.
            failure = ProcessingFailure("1.0", "ADAPTER_ERROR", stage, True)
            return self._dead_letter(failure, topic, partition, offset, message_key, digest)

    # topic으로 원본 종류를 정하고, 알 수 없으면 로그의 source 필드로 판단한다.
    def _normalize(self, record: Any, topic: str, digest: str):
        is_was = topic == self._settings.was_topic or (
            topic != self._settings.nginx_topic
            and isinstance(record, dict)
            and record.get("source") == "was"
        )
        if is_was:
            return normalize_was_log(
                record,
                self._policy,
                pseudonym_key=self._settings.pseudonym_key,
                default_environment=self._settings.default_environment,
            )
        return normalize_nginx_log(
            record,
            self._policy,
            pseudonym_key=self._settings.pseudonym_key,
            default_environment=self._settings.default_environment,
            # 원본에 ID가 없으면 같은 바이트에 항상 같은 ID를 만들어 중복 저장을 막는다.
            fallback_event_id=stable_id("nginx", digest),
        )

    # 마스킹 로그와 보안 이벤트를 만들고 발행 전에 마스킹 누락을 다시 확인한다.
    def _success(self, normalized, result, detected_at) -> PipelineResult:
        masked = result.masked_log
        extra = (
            prompt_injection.detect(normalized.log["body"])
            if normalized.prompt_injection
            else []
        )
        risk_level, risk_score, detected_rules = outbound.merge_risk(masked, extra)
        masked_message = outbound.masked_log_message(
            masked,
            policy=self._policy,
            source_kind=normalized.source_kind,
            risk_level=risk_level,
            risk_score=risk_score,
            detected_rules=detected_rules,
        )
        messages = [
            OutboundMessage(self._settings.masked_logs_topic, self._key(masked), masked_message)
        ]
        if result.security_event is not None or extra:
            entries = outbound.build_detection_entries(
                outbound.security_event_id(masked), extra
            )
            event_message = outbound.security_event_message(
                masked,
                result.security_event,
                entries,
                policy=self._policy,
                source_kind=normalized.source_kind,
                risk_level=risk_level,
                risk_score=risk_score,
                detected_at=detected_at,
            )
            messages.append(
                OutboundMessage(
                    self._settings.security_events_topic, self._key(masked), event_message
                )
            )
        for message in messages:
            if contains_sensitive(
                message.value.get("masked_message"),
                message.value.get("masked_excerpt"),
                message.value.get("safe_metadata"),
            ):
                raise AdapterError("UNSAFE_OUTPUT", "DETECT_MASK")
        return PipelineResult(
            messages=tuple(messages),
            failed=False,
            source_kind=normalized.source_kind,
            risk_level=risk_level,
        )

    # 같은 요청의 결과를 같은 partition으로 보내 순서를 유지한다.
    @staticmethod
    def _key(masked) -> str:
        return masked.request_id or masked.event_id

    # 실패는 원문 없이 위치 정보만 담아 dead-letter로 보낸다.
    def _dead_letter(
        self,
        failure: ProcessingFailure,
        topic: str,
        partition: int,
        offset: int,
        message_key: str | None,
        digest: str,
    ) -> PipelineResult:
        value = outbound.dead_letter_message(
            failure,
            topic=topic,
            partition=partition,
            offset=offset,
            consumer_group=self._settings.group_id,
            message_key=message_key,
            payload_hash=digest,
        )
        message = OutboundMessage(self._settings.dead_letter_topic, digest[:32], value)
        return PipelineResult(
            messages=(message,), failed=True, error_code=failure.error_code
        )
