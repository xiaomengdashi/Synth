from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DATABASE_PATH = DATA_DIR / "synthai.db"
DEFAULT_MEDIA_DIR = DATA_DIR / "media"
DEFAULT_ARTICLES_DIR = DATA_DIR / "articles"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".backend.env", extra="ignore")

    DATABASE_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH}"
    MEDIA_DIR: str = str(DEFAULT_MEDIA_DIR)
    ARTICLES_DIR: str = str(DEFAULT_ARTICLES_DIR)
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True
    FRONTEND_URL: str = "http://localhost:3000"

settings = Settings()
