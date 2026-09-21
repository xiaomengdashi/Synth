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
    biliSessdata: str | None = None
    biliJct: str | None = None
    biliBuvid3: str | None = None


def _public_config(data: dict) -> dict:
    """Return only configuration fields that are still supported by the app."""
    supported_keys = {
        "apiKey",
        "baseUrl",
        "modelName",
        "biliSessdata",
        "biliJct",
        "biliBuvid3",
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
        "biliSessdata": "",
        "biliJct": "",
        "biliBuvid3": "",
    }

@router.post("")
async def save_config(config: AppConfigModel):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config.model_dump() if hasattr(config, 'model_dump') else config.dict(), f)
    return {"status": "success"}
