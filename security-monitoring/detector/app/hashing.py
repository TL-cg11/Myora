# 로그 비교용 해시와 재처리 중복 방지용 ID를 생성한다. 해시는 암호화가 아니다.
import hashlib
import hmac
import uuid


# 원본 본문 전체의 SHA-256 지문을 반환한다. 원문을 복호화하는 기능은 없다.
def body_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# 비밀키가 있을 때만 개별 값의 HMAC 지문을 만든다. 키가 없으면 None이다.
def fingerprint(text: str, key: bytes | None) -> str | None:
    # Low-entropy PII can be guessed from plain SHA-256. Omit per-value
    # fingerprints unless the deployment supplies a private HMAC key.
    if key is None:
        return None
    return "hmac-sha256:" + hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


# 같은 입력 요소와 버전으로 항상 같은 UUID를 만들어 C의 중복 저장 방지를 돕는다.
def stable_id(*parts: str) -> str:
    import json
    return str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(parts, ensure_ascii=True)))
