import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.deepseek.face")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "luck-was")
    app_env: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    db_host: str = os.getenv("DB_HOST", "100.104.124.29")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "luck_db")
    db_user: str = os.getenv("DB_USER", "luck_user")
    db_password: str = os.getenv("DB_PASSWORD", "Luck1234!")
    sazu_api_key: str = os.getenv("SAZU_API_KEY", "")
    sazu_api_url: str = os.getenv("SAZU_API_URL", "https://api.sazu.app/v1/sazu/calculate")
    deepseek_face_api_key: str = os.getenv("DEEPSEEK_FACE_API_KEY", "")
    deepseek_face_model: str = os.getenv("DEEPSEEK_FACE_MODEL", "deepseek-v4-flash")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


settings = Settings()
