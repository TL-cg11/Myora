import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
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
    
    deepseek_saju_api_key: str = os.getenv("DEEPSEEK_SAJU_API_KEY", "")
    deepseek_tarot_api_key: str = os.getenv("DEEPSEEK_TAROT_API_KEY", "")
    deepseek_face_api_key: str = os.getenv("DEEPSEEK_FACE_API_KEY", "")
    
    deepseek_saju_model: str = os.getenv("DEEPSEEK_SAJU_MODEL", "deepseek-v4-flash")
    deepseek_tarot_model: str = os.getenv("DEEPSEEK_TAROT_MODEL", "deepseek-v4-flash")
    deepseek_face_model: str = os.getenv("DEEPSEEK_FACE_MODEL", "deepseek-v4-flash")
    
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # 타로 채팅용. 키가 없으면 LLM 을 호출하지 않고 규칙 기반 답변만 쓴다.
    deepseek_tarot_enabled: bool = bool(os.getenv("DEEPSEEK_TAROT_API_KEY"))
    
    # 사용자가 채팅 앞에서 기다리는 시간이라 넉넉하게 잡지 않는다.
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "20"))

    # 결과 화면 채팅에서 물어볼 수 있는 횟수. 사주·관상·타로가 같은 값을 쓴다.
    # 화면에도 같은 숫자가 필요한데 브라우저는 이 파일을 못 읽으므로
    # /api/config 가 내려준다(app/main.py).
    chat_question_limit: int = int(os.getenv("CHAT_QUESTION_LIMIT", "5"))

    @property
    def tarot_llm_enabled(self) -> bool:
        return bool(self.deepseek_tarot_api_key)


settings = Settings()
