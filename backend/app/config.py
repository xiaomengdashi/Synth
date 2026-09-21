from pathlib import Path

from pydantic_settings import BaseSettings


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DATABASE_PATH = DATA_DIR / "synthai.db"
DEFAULT_MEDIA_DIR = DATA_DIR / "media"
DEFAULT_ARTICLES_DIR = DATA_DIR / "articles"
DEFAULT_CONFIG_FILE = DATA_DIR / "config.json"


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH}"
    MEDIA_DIR: str = str(DEFAULT_MEDIA_DIR)
    ARTICLES_DIR: str = str(DEFAULT_ARTICLES_DIR)
    CONFIG_FILE: str = str(DEFAULT_CONFIG_FILE)
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True
    FRONTEND_URL: str = "http://localhost:3000"
    # WeChat CAPTCHA pages require a user-controlled session; the service does
    # not open a browser automatically when importing a link.
    WECHAT_BROWSER_ENABLED: bool = False
    WECHAT_BROWSER_PROFILE_DIR: str = str(DATA_DIR / "wechat-browser-profile")
    WECHAT_BROWSER_EXECUTABLE_PATH: str = ""
    WECHAT_BROWSER_HEADLESS: bool = False
    WECHAT_BROWSER_TIMEOUT_MS: int = 45000
    WECHAT_BROWSER_VERIFY_TIMEOUT_MS: int = 180000

    class Config:
        env_file = ".backend.env"
        extra = "ignore"


settings = Settings()
