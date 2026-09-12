# 전체 처리 엔진: 입력 검증 → 재귀 탐지·마스킹 → 위험도 계산 → C용 이벤트 생성.
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import re
from collections.abc import Callable

from . import jsonio
from .hashing import body_hash, fingerprint, stable_id
from .masking import mask
from .models import (Detection, InputError, MaskedLog, NormalizedLog,
                     ProcessingFailure, ProcessingResult, SecurityEvent)
from .risk import calculate_risk
from .rules import pii, secrets
from .rules.ner import NERRecognizer
from .rules.pii_context import PIICandidateVerifier

# 규칙/정책 변경 시 버전을 올려 재처리 결과와 변경 이력을 구분한다.
VERSION = "1.2.0"
POLICY_VERSION = "1"
# 구분자와 대소문자를 정규화한 필드명 → (규칙, 분류, 점수).
# 이름처럼 문장 패턴만으로 찾기 어려운 정보도 알려진 필드에 있으면 전체를 가린다.
SENSITIVE_KEYS = {
    "name": ("PERSON_NAME", "PII", 50), "customername": ("PERSON_NAME", "PII", 50),
    "fullname": ("PERSON_NAME", "PII", 50), "성명": ("PERSON_NAME", "PII", 50),
    "이름": ("PERSON_NAME", "PII", 50),
    "birthdate": ("BIRTH_DATE", "PII", 50), "dateofbirth": ("BIRTH_DATE", "PII", 50),
    "dob": ("BIRTH_DATE", "PII", 50), "생년월일": ("BIRTH_DATE", "PII", 50),
    "password": ("PASSWORD", "SECRET", 90), "passwd": ("PASSWORD", "SECRET", 90),
    "pwd": ("PASSWORD", "SECRET", 90), "dbpassword": ("PASSWORD", "SECRET", 90),
    "secret": ("API_KEY", "SECRET", 90), "apikey": ("API_KEY", "SECRET", 90),
    "token": ("API_KEY", "SECRET", 90), "accesstoken": ("API_KEY", "SECRET", 90),
    "refreshtoken": ("API_KEY", "SECRET", 90),
    "authorization": ("AUTHORIZATION", "SECRET", 90),
    "cookie": ("AUTHORIZATION", "SECRET", 90), "setcookie": ("AUTHORIZATION", "SECRET", 90),
    "privatekey": ("PRIVATE_KEY", "SECRET", 100),
    "databaseurl": ("DB_CONNECTION_STRING", "SECRET", 95),
    "phone": ("PHONE_NUMBER", "PII", 50), "phonenumber": ("PHONE_NUMBER", "PII", 50),
    "email": ("EMAIL_ADDRESS", "PII", 30), "rrn": ("KR_RRN", "PII", 85),
}


# 개인정보·비밀정보 규칙을 합치고 DB URL 내부 이메일 후보의 중복 집계를 제외한다.
def detect(text: str, ner_recognizer: NERRecognizer | None = None,
           pii_verifier: PIICandidateVerifier | None = None,
           on_context_exemption: Callable[[str], None] | None = None) -> list[Detection]:
    secret_matches = secrets.detect(text)
    # URL credentials look like email addresses; classify them as the enclosing
    # database secret to avoid inflating PII counts.
    containers = [d for d in secret_matches if d.rule_id in {"DB_CONNECTION_STRING", "PRIVATE_KEY"}]
    pii_matches = pii.detect(text)
    if pii_verifier is not None:
        original = pii_matches
        pii_matches = pii_verifier.verify(text, original)
        kept = {(d.rule_id, d.start, d.end) for d in pii_matches}
        if on_context_exemption is not None:
            for candidate in original:
                if (candidate.rule_id, candidate.start, candidate.end) not in kept:
                    on_context_exemption(text[candidate.start:candidate.end])
    if ner_recognizer is not None:
        pii_matches += ner_recognizer.detect(text)
    pii_matches = [d for d in pii_matches
                   if not any(c.start <= d.start and d.end <= c.end for c in containers)]
    return pii_matches + secret_matches


# 한 건의 입력을 끝까지 처리한다. 어느 단계든 실패하면 원문/부분 성공 결과를 반환하지 않는다.
# "{" 또는 "[" 로 시작하는 문자열 가운데 실제 JSON 문서로 볼 수 있는 것만 고른다.
# 여는 괄호 다음 토큰이 JSON 값(문자열·객체·배열·숫자·true/false/null)이나 닫는 괄호가 아니면
# "[질문] ..." 같은 일반 문장이다. 괄호만 있는 잘린 문자열은 JSON 으로 보고 fail closed 한다.
_JSON_VALUE_START = re.compile(r'^(?:"|\{|\[|\]|\}|-?\d|true\b|false\b|null\b)')


def _looks_like_json(value: str) -> bool:
    stripped = value.lstrip()
    if not stripped.startswith(("{", "[")):
        return False
    rest = stripped[1:].lstrip()
    if not rest:
        return True
    if stripped[0] == "{":
        return rest[0] in '"}'
    return _JSON_VALUE_START.match(rest) is not None


def process_log(data: dict | NormalizedLog, *, fingerprint_key: bytes | None = None,
                detected_at: datetime | None = None,
                ner_recognizer: NERRecognizer | None = None,
                pii_verifier: PIICandidateVerifier | None = None) -> ProcessingResult:
    """Pure processing boundary: failures never return a partial/raw output."""
    stage = "VALIDATE"
    try:
        payload = asdict(data) if isinstance(data, NormalizedLog) else data
        log = NormalizedLog.from_dict(payload)
        if len(json.dumps(payload, ensure_ascii=True, allow_nan=False)) > 1_000_000:
            raise InputError("INPUT_LIMIT")
        if fingerprint_key is not None and (not isinstance(fingerprint_key, bytes) or len(fingerprint_key) < 32):
            raise InputError("INVALID_FINGERPRINT_KEY")
        # Identity fields are copied to C, so reject sensitive-looking values
        # rather than changing IDs and breaking request correlation.
        for name in ("event_id", "request_id", "environment", "service", "source_type", "event_name"):
            value = getattr(log, name)
            if value is not None and (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", value) or detect(value)):
                raise InputError("UNSAFE_METADATA")

        stage = "DETECT_MASK"
        findings: list[Detection] = []
        fingerprints: dict[tuple, str | None] = {}
        context_exemptions: set[str] = set()

        # 원문 대신 탐지 위치와 선택적 HMAC만 보관하고 탐지 건수 상한을 적용한다.
        def remember(d: Detection, value: str, path: str):
            if len(findings) >= 10_000:
                raise InputError("DETECTION_LIMIT")
            item = replace(d, field=path)
            findings.append(item)
            fingerprints[(path, item.rule_id, item.start, item.end)] = fingerprint(value[d.start:d.end], fingerprint_key)

        # 한 문자열에 규칙을 적용하고 발견 위치를 기록한 뒤 마스킹 문자열을 반환한다.
        def text_value(value: str, path: str):
            def exempt(raw: str) -> None:
                if len(context_exemptions) >= 1000:
                    raise InputError("DETECTION_LIMIT")
                context_exemptions.add(hashlib.sha256(raw.encode("utf-8")).hexdigest())

            detected = detect(
                value, ner_recognizer, pii_verifier,
                on_context_exemption=exempt,
            )
            for d in detected:
                remember(d, value, path)
            return mask(value, detected)

        nodes = [0]

        # 객체·배열·내부 JSON 문자열을 재귀 순회하여 중첩된 민감정보도 처리한다.
        def walk(value, path, depth=0):
            nodes[0] += 1
            if depth > 12 or nodes[0] > 5000:
                raise InputError("INPUT_LIMIT")
            if isinstance(value, dict):
                result = {}
                for index, (key, child) in enumerate(value.items()):
                    # Ordinal paths avoid reflecting arbitrary sensitive keys in evidence.
                    child_path = f"{path}/@{index}"
                    safe_key = text_value(key, child_path + "/key")
                    if safe_key in result:
                        raise InputError("MASKED_KEY_COLLISION")
                    key_rule = SENSITIVE_KEYS.get(re.sub(r"[_\s-]", "", key).lower())
                    if key_rule and child is not None and child != "" and not (isinstance(child, str) and re.fullmatch(r"\[REDACTED(?:_[A-Z_]+)?\]", child)):
                        rule, category, score = key_rule
                        raw = child if isinstance(child, str) else json.dumps(child, ensure_ascii=False)
                        level = "CRITICAL" if score >= 95 else "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
                        d = Detection(rule, category, level, score, 1.0, 0, len(raw), "[REDACTED]")
                        remember(d, raw, child_path)
                        result[safe_key] = "[REDACTED]"
                    else:
                        result[safe_key] = walk(child, child_path, depth + 1)
                return result
            if isinstance(value, list):
                return [walk(v, f"{path}/{i}", depth + 1) for i, v in enumerate(value)]
            if isinstance(value, str):
                # Parse embedded JSON so escaped sensitive values and name/date
                # fields are covered. Malformed object-like strings fail closed.
                # Plain text that merely starts with a bracket ("[안전 검사로 저장하지
                # 않은 질문]", "[질문] ...") is not JSON and takes the regular text path.
                if _looks_like_json(value) and not value.startswith("[REDACTED"):
                    try:
                        embedded = jsonio.loads(value)
                    except (ValueError, RecursionError):
                        raise InputError("INVALID_EMBEDDED_JSON") from None
                    return json.dumps(walk(embedded, path + "/json", depth + 1), ensure_ascii=False)
                return text_value(value, path)
            if type(value) in {int, float}:
                # Keep ordinary numeric metadata numeric, but mask PII candidates.
                raw = str(value)
                safe = text_value(raw, path)
                return safe if raw != safe else value
            return value

        # 본문과 속성 모두 검사가 끝난 뒤에만 성공 모델을 만든다.
        masked_body = walk(log.body, "/body")
        masked_attributes = walk(log.attributes, "/attributes")
        level, score = calculate_risk(findings)
        digest = body_hash(log.body)
        masked = MaskedLog(log.schema_version, log.event_id, log.request_id,
                           log.timestamp, log.environment, log.service, log.source_type,
                           log.event_name, log.severity, masked_body, masked_attributes,
                           digest, sorted({d.rule_id for d in findings}), level, score,
                           VERSION, POLICY_VERSION,
                           tuple(sorted(context_exemptions)))
        if not findings:
            return ProcessingResult(masked_log=masked)

        stage = "BUILD_EVENT"
        event_id = stable_id(log.environment, log.service, log.event_id, VERSION, POLICY_VERSION)
        # C 테이블에서는 사건 한 건 아래 규칙별 여러 탐지를 저장한다.
        grouped: dict[str, list[Detection]] = {}
        for d in findings:
            grouped.setdefault(d.rule_id, []).append(d)
        entries = []
        for rule_id, matches in sorted(grouped.items()):
            sample = matches[0]
            evidence = fingerprints[(sample.field, sample.rule_id, sample.start, sample.end)] if len(matches) == 1 else None
            entries.append({"detection_id": stable_id(event_id, rule_id, sample.rule_version),
                            "rule_id": rule_id, "rule_version": sample.rule_version,
                            "category": sample.category, "entity_type": rule_id,
                            "risk_level": sample.risk_level,
                            "confidence": max(d.confidence for d in matches),
                            "match_count": len(matches), "evidence_fingerprint": evidence,
                            "locations": [{"field": d.field, "start": d.start, "end": d.end} for d in matches]})
        # 테스트에서 시각을 주입할 수 있고 실제 실행에서는 현재 UTC를 사용한다.
        clock = detected_at or datetime.now(timezone.utc)
        if clock.utcoffset() is None:
            raise InputError("INVALID_DETECTED_AT")
        stamp = lambda dt: dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        # SecurityEvent 발췌문은 exemption 해시가 함께 전달되지 않는 알림에서도
        # 안전해야 하므로 문맥상 비PII로 승인된 형식까지 보수적으로 다시 가린다.
        event_excerpt = mask(masked_body, pii.detect(masked_body))
        event = SecurityEvent("1.0", event_id, log.event_id, log.request_id,
                              stamp(datetime.fromisoformat(log.timestamp.replace("Z", "+00:00"))),
                              stamp(clock), log.environment, log.service, log.source_type,
                              log.event_name, level, score, VERSION, POLICY_VERSION,
                              event_excerpt[:1000], digest, entries, {})
        return ProcessingResult(masked_log=masked, security_event=event)
    except InputError as exc:
        return ProcessingResult(failure=ProcessingFailure("1.0", str(exc), stage, False))
    except Exception:
        # Do not stringify exceptions: parsers and clients may embed raw payloads.
        return ProcessingResult(failure=ProcessingFailure("1.0", "PROCESSING_ERROR", stage, True))
