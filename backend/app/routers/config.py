from fastapi import APIRouter
from pydantic import BaseModel
import json
import os
from app.config import settings

router = APIRouter()

CONFIG_FILE = settings.CONFIG_FILE

class AppConfigModel(BaseModel):
    apiKey: str
    baseUrl: str
    modelName: str
    tikhubApiKey: str | None = None


def _public_config(data: dict) -> dict:
    """Return only configuration fields that are still supported by the app."""
    supported_keys = {
        "apiKey",
        "baseUrl",
        "modelName",
        "tikhubApiKey",
    }
    return {key: data.get(key, "") for key in supported_keys}

@router.get("")
async def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return _public_config(json.load(f))
        except Exception:
            pass
    return {
        "apiKey": "",
        "baseUrl": "",
        "modelName": "",
        "tikhubApiKey": "",
    }

def _load_stored_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                return stored
        except Exception:
            pass
    return {}


@router.post("")
async def save_config(config: AppConfigModel):
    payload = config.model_dump() if hasattr(config, 'model_dump') else config.dict()
    # 前端旧版本不携带 tikhubApiKey 时，保留已存储的 Token 而不是清空。
    if payload.get("tikhubApiKey") is None:
        payload["tikhubApiKey"] = _load_stored_config().get("tikhubApiKey")
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(payload, f)
    return {"status": "success"}
