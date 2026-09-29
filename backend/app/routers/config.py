import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import BACKEND_DIR
from app.services import settings_store

router = APIRouter()

# 旧版 JSON 配置文件：启动时自动迁移到 SQLite 后改名留存
LEGACY_CONFIG_FILE = BACKEND_DIR / "data" / "config.json"


class AppConfigModel(BaseModel):
    apiKey: str = ""
    baseUrl: str = ""
    modelName: str = ""


async def migrate_legacy_config() -> bool:
    """把 data/config.json 的配置项导入 app_settings 表（不覆盖已有值），成功后改名备份。"""
    if not LEGACY_CONFIG_FILE.exists():
        return False
    try:
        legacy = json.loads(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(legacy, dict):
        return False

    existing = await settings_store.load_settings()
    values = {
        key: str(legacy.get(key) or "").strip()
        for key in settings_store.SUPPORTED_KEYS
        if str(legacy.get(key) or "").strip() and not existing.get(key)
    }
    if values:
        await settings_store.save_settings(values)
    LEGACY_CONFIG_FILE.rename(LEGACY_CONFIG_FILE.with_suffix(".json.migrated"))
    return True


@router.get("")
async def get_config():
    return settings_store.public_settings(await settings_store.load_settings())


async def get_runtime_config() -> dict:
    """Internal use only: background fetches need the saved credential."""
    return await settings_store.load_settings()


@router.post("")
async def save_config(config: AppConfigModel):
    # TikHub credentials can only change via the verified /tikhub/key endpoint.
    await settings_store.save_settings(config.model_dump())
    return {"status": "success", **settings_store.public_settings(await settings_store.load_settings())}
