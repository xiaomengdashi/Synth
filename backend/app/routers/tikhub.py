"""TikHub 管理接口：Key 设置/验证 与账户信息查询。"""

import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.fetchers.tikhub import (
    TikHubError,
    TikHubNotConfiguredError,
    fetch_tikhub_account,
    verify_tikhub_token,
)

router = APIRouter()

CONFIG_FILE = settings.CONFIG_FILE


class TikHubKeyPayload(BaseModel):
    apiKey: str


def _load_stored_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                return stored
        except Exception:
            pass
    return {}


def _resolve_effective_token() -> str:
    """已保存的 config.json 优先，其次环境变量（与抓取链路的解析顺序一致）。"""
    stored = _load_stored_config().get("tikhubApiKey")
    return str(stored or "").strip() or os.environ.get("TIKHUB_API_TOKEN", "").strip()


@router.get("/account")
async def get_tikhub_account():
    """查询当前 Key 的 TikHub 账户信息（余额、今日用量、Key 状态）。"""
    token = _resolve_effective_token()
    if not token:
        return {"configured": False}

    try:
        account = fetch_tikhub_account({"tikhubApiKey": token})
    except TikHubNotConfiguredError:
        return {"configured": False}
    except TikHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"configured": True, **account}


@router.post("/key")
async def set_tikhub_key(data: TikHubKeyPayload):
    """验证并保存 TikHub API Token（验证通过才落盘）。"""
    token = str(data.apiKey or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="API Token 不能为空。")

    try:
        summary = verify_tikhub_token(token)
    except TikHubError as exc:
        raise HTTPException(status_code=400, detail=f"Token 验证失败：{exc}") from exc

    stored = _load_stored_config()
    stored["tikhubApiKey"] = token
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(stored, f, ensure_ascii=False, indent=2)

    return {"status": "success", "message": "Token 验证通过并已保存。", "account": summary}
