# 어댑터 실행 설정: Kafka 주소·topic·비밀키를 환경변수로만 주입한다.
"""Environment-driven settings for the Kafka masking adapter."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping

# 원본 topic은 A가 운영하는 수집 topic, 결과 topic은 C가 소비하는 계약 topic이다.
DEFAULT_INPUT_TOPICS = "myohan.was.app,myohan.nginx.access"
DEFAULT_GROUP_ID = "myohan-security-masking"
DEFAULT_MASKED_LOGS_TOPIC = "myohan.masked-logs"
DEFAULT_SECURITY_EVENTS_TOPIC = "myohan.security-events"
DEFAULT_DEAD_LETTER_TOPIC = "myohan.dead-letter"
# C 계약의 environment enum. 여기에 없는 값은 결과 topic에 실을 수 없다.
ALLOWED_ENVIRONMENTS = ("development", "test", "staging", "production")
# Kafka 인증 옵션은 luck-nginx sink와 같은 환경변수 이름을 사용한다.
OPTIONAL_CLIENT_KEYS = {
    "security.protocol": "KAFKA_SECURITY_PROTOCOL",
    "sasl.mechanism": "KAFKA_SASL_MECHANISM",
    "sasl.username": "KAFKA_SASL_USERNAME",
    "sasl.password": "KAFKA_SASL_PASSWORD",
    "ssl.ca.location": "KAFKA_SSL_CA_LOCATION",
}
MINIMUM_KEY_BYTES = 32


class ConfigError(RuntimeError):
    """설정이 없거나 안전하지 않아 프로세스를 시작할 수 없는 상태."""


# 값이 비어 있으면 기본값을 쓰고, 기본값이 없으면 시작 자체를 막는다.
def _text(env: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = (env.get(name) or "").strip()
    if value:
        return value
    if default is None:
        raise ConfigError(f"필수 환경변수가 없습니다: {name}")
    return default


# 가명화·지문 키는 짧으면 사전 대입으로 원본을 되찾을 수 있어 길이를 강제한다.
def _secret(env: Mapping[str, str], name: str, *, required: bool) -> bytes | None:
    raw = env.get(name) or ""
    if not raw:
        if required:
            raise ConfigError(
                f"필수 비밀키가 없습니다: {name} "
                f"(UTF-8 {MINIMUM_KEY_BYTES}바이트 이상)"
            )
        return None
    key = raw.encode("utf-8")
    if len(key) < MINIMUM_KEY_BYTES:
        raise ConfigError(f"{name}는 UTF-8 {MINIMUM_KEY_BYTES}바이트 이상이어야 합니다.")
    return key


@dataclass(frozen=True)
# 어댑터 한 프로세스의 실행 설정. 생성 후에는 변경하지 않는다.
class Settings:
    bootstrap_servers: str  # Kafka broker 주소 목록
    group_id: str  # 원본 topic 소비자 그룹
    input_topics: tuple[str, ...]  # 소비할 원본 topic
    was_topic: str  # WAS JSON 로그 topic
    nginx_topic: str  # Nginx access 로그 topic
    masked_logs_topic: str  # 마스킹 로그 발행 topic
    security_events_topic: str  # 보안 이벤트 발행 topic
    dead_letter_topic: str  # 실패 메타데이터 발행 topic
    pseudonym_key: bytes  # user_id/guest_key 가명화 HMAC 키
    fingerprint_key: bytes | None  # 탐지 증거 지문 HMAC 키. 없으면 지문을 남기지 않는다
    default_environment: str  # 원본에 environment가 없을 때 사용할 값
    auto_offset_reset: str  # 저장된 offset이 없을 때 시작 위치
    poll_timeout: float  # consumer poll 대기 시간(초)
    flush_timeout: float  # 발행 완료 대기 시간(초)
    publish_attempts: int  # 발행 재시도 횟수
    client_options: dict[str, Any]  # 인증 등 공통 Kafka 옵션

    # consumer는 결과 발행이 끝난 뒤 직접 commit하므로 자동 commit을 끈다.
    def consumer_config(self) -> dict[str, Any]:
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.group_id,
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": False,
        }
        config.update(self.client_options)
        return config

    # 결과를 잃지 않도록 멱등 producer와 전체 복제 확인을 사용한다.
    def producer_config(self) -> dict[str, Any]:
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": f"{self.group_id}-producer",
            "enable.idempotence": True,
            "acks": "all",
        }
        config.update(self.client_options)
        return config


# 환경변수를 읽어 설정을 만든다. 잘못된 값은 실행 전에 즉시 실패시킨다.
def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    topics = tuple(
        topic.strip()
        for topic in _text(env, "ADAPTER_INPUT_TOPICS", DEFAULT_INPUT_TOPICS).split(",")
        if topic.strip()
    )
    if not topics:
        raise ConfigError("ADAPTER_INPUT_TOPICS에 topic이 하나도 없습니다.")
    default_environment = _text(env, "ADAPTER_DEFAULT_ENVIRONMENT", "production")
    if default_environment not in ALLOWED_ENVIRONMENTS:
        raise ConfigError(
            "ADAPTER_DEFAULT_ENVIRONMENT는 "
            f"{', '.join(ALLOWED_ENVIRONMENTS)} 중 하나여야 합니다."
        )
    attempts = int(_text(env, "ADAPTER_PUBLISH_ATTEMPTS", "3"))
    if attempts < 1:
        raise ConfigError("ADAPTER_PUBLISH_ATTEMPTS는 1 이상이어야 합니다.")
    client_options = {
        key: env[name]
        for key, name in OPTIONAL_CLIENT_KEYS.items()
        if (env.get(name) or "").strip()
    }
    return Settings(
        bootstrap_servers=_text(env, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        group_id=_text(env, "ADAPTER_GROUP_ID", DEFAULT_GROUP_ID),
        input_topics=topics,
        was_topic=_text(env, "ADAPTER_WAS_TOPIC", "myohan.was.app"),
        nginx_topic=_text(env, "ADAPTER_NGINX_TOPIC", "myohan.nginx.access"),
        masked_logs_topic=_text(env, "ADAPTER_MASKED_LOGS_TOPIC", DEFAULT_MASKED_LOGS_TOPIC),
        security_events_topic=_text(
            env, "ADAPTER_SECURITY_EVENTS_TOPIC", DEFAULT_SECURITY_EVENTS_TOPIC
        ),
        dead_letter_topic=_text(env, "ADAPTER_DEAD_LETTER_TOPIC", DEFAULT_DEAD_LETTER_TOPIC),
        pseudonym_key=_secret(env, "MASKING_PSEUDONYM_KEY", required=True),
        fingerprint_key=_secret(env, "DETECTOR_FINGERPRINT_KEY", required=False),
        default_environment=default_environment,
        auto_offset_reset=_text(env, "KAFKA_AUTO_OFFSET_RESET", "earliest"),
        poll_timeout=float(_text(env, "ADAPTER_POLL_TIMEOUT", "1.0")),
        flush_timeout=float(_text(env, "ADAPTER_FLUSH_TIMEOUT", "10.0")),
        publish_attempts=attempts,
        client_options=client_options,
    )
