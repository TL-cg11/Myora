import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# 아래 세 파일은 기존 배포 환경과의 호환을 위해 계속 읽는다.
load_dotenv(BASE_DIR / ".env.deepseek.face")
load_dotenv(BASE_DIR / ".env.deepseek.saju")
load_dotenv(BASE_DIR / ".env.deepseek.tarot")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    app_name: str = os.getenv("APP_NAME", "luck-was")
    app_env: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    db_host: str = os.getenv("DB_HOST", "100.104.124.29")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "luck_db")
    db_user: str = os.getenv("DB_USER", "luck_user")
    db_password: str = os.getenv("DB_PASSWORD", "Luck1234!")

    # 일반 회원 인증 정책. 운영에서 환경변수로 조정할 수 있다.
    auth_session_hours: int = int(os.getenv("AUTH_SESSION_HOURS", "1"))
    auth_max_failed_attempts: int = int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5"))
    auth_lockout_minutes: int = int(os.getenv("AUTH_LOCKOUT_MINUTES", "60"))

    # 보안 관제 API는 일반 서비스 데이터와 분리된 DB/계정을 사용한다.
    security_database_url: str = os.getenv("SECURITY_DATABASE_URL", "")
    security_db_host: str = os.getenv(
        "SECURITY_DB_HOST", os.getenv("DB_HOST", "100.104.124.29")
    )
    security_db_port: int = int(
        os.getenv("SECURITY_DB_PORT", os.getenv("DB_PORT", "3306"))
    )
    security_db_name: str = os.getenv("SECURITY_DB_NAME", "security_monitoring")
    security_db_user: str = os.getenv("SECURITY_DB_USER", "security_monitoring_api")
    security_db_password: str = os.getenv("SECURITY_DB_PASSWORD", "")
    # {"<sha256 hex>": "actor-id"} 형태. 원문 Bearer token은 저장하지 않는다.
    security_auth_token_hashes: str = os.getenv("SECURITY_AUTH_TOKEN_HASHES", "{}")

    # AI 공통 설정: 서비스별 키/모델은 기존 환경변수로 재정의할 수 있다.
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_saju_api_key: str = os.getenv("DEEPSEEK_SAJU_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_tarot_api_key: str = os.getenv("DEEPSEEK_TAROT_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_face_api_key: str = os.getenv("DEEPSEEK_FACE_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_saju_model: str = os.getenv("DEEPSEEK_SAJU_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    deepseek_tarot_model: str = os.getenv("DEEPSEEK_TAROT_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    deepseek_face_model: str = os.getenv("DEEPSEEK_FACE_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    ai_request_timeout: float = float(os.getenv("AI_REQUEST_TIMEOUT", os.getenv("LLM_TIMEOUT", "20")))
    ai_connect_timeout: float = float(os.getenv("AI_CONNECT_TIMEOUT", "5"))
    # 검사 호출은 JSON 판정만 받으므로 생성보다 짧게 잡는다. 정상 상담은 검사 2회와
    # 생성 1회를 순차로 하므로 전체 제한은 그 합보다 커야 한다(__post_init__에서 검증).
    ai_check_timeout: float = float(os.getenv("AI_CHECK_TIMEOUT", "10"))
    ai_total_timeout: float = float(os.getenv("AI_TOTAL_TIMEOUT", "45"))
    ai_max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "700"))
    ai_check_max_tokens: int = int(os.getenv("AI_CHECK_MAX_TOKENS", "250"))
    ai_history_limit: int = int(os.getenv("AI_HISTORY_LIMIT", "10"))
    ai_message_max_chars: int = int(os.getenv("AI_MESSAGE_MAX_CHARS", "1500"))
    ai_context_max_chars: int = int(os.getenv("AI_CONTEXT_MAX_CHARS", "8000"))
    ai_answer_max_chars: int = int(os.getenv("AI_ANSWER_MAX_CHARS", "4000"))
    chat_question_limit: int = int(os.getenv("CHAT_QUESTION_LIMIT", "5"))
    chat_question_limit_admin: int = int(os.getenv("CHAT_QUESTION_LIMIT_ADMIN", "20"))
    ai_guardrail_model: str = os.getenv("AI_GUARDRAIL_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    display_masking_host: str = os.getenv("ADAPTER_DISPLAY_API_HOST", "127.0.0.1")
    display_masking_port: int = int(os.getenv("ADAPTER_DISPLAY_API_PORT", "8765"))

    def __post_init__(self):
        for name in ("ai_request_timeout", "ai_connect_timeout", "ai_check_timeout",
                     "ai_total_timeout", "ai_max_tokens",
                     "ai_check_max_tokens", "ai_history_limit", "ai_message_max_chars",
                     "ai_context_max_chars", "ai_answer_max_chars", "chat_question_limit",
                     "chat_question_limit_admin"):
            value = getattr(self, name)
            if not 0 < value < float("inf"):
                raise ValueError(f"{name} must be finite and positive")
        # 예산이 모자라면 개별 호출은 정상인데 전체가 시간 초과로 죽는다. 그 상태에서는
        # 정상 질문도 장애 응답만 받으므로 조용히 넘기지 않고 시작 시점에 알린다.
        sequential = self.ai_check_timeout * 2 + self.ai_request_timeout
        if self.ai_total_timeout < sequential:
            raise ValueError(
                "AI_TOTAL_TIMEOUT must cover AI_CHECK_TIMEOUT*2 + AI_REQUEST_TIMEOUT "
                f"({self.ai_total_timeout} < {sequential})"
            )
        if self.display_masking_host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("ADAPTER_DISPLAY_API_HOST must be a loopback address")
        if not 1 <= self.display_masking_port <= 65535:
            raise ValueError("ADAPTER_DISPLAY_API_PORT must be between 1 and 65535")

    @property
    def tarot_llm_enabled(self) -> bool:
        return bool(self.deepseek_tarot_api_key)


settings = Settings()
