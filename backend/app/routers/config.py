from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services import settings_store

from app.routers.admin_auth import require_admin

router = APIRouter()


class AppConfigModel(BaseModel):
    apiKey: str = ""
    baseUrl: str = ""
    modelName: str = ""
    minimaxApiKey: str = ""
    imapHost: str = ""
    imapUser: str = ""
    imapPassword: str = ""
    imapSenderWhitelist: str = ""
    # 可调参数：留空即恢复默认（默认值见 settings_store.SETTING_DEFAULTS）
    tikhubApiBase: str = ""
    bilibiliProxy: str = ""
    minimaxApiBase: str = ""
    llmTemperature: str = ""
    llmMaxTokens: str = ""
    llmTimeoutSeconds: str = ""
    summaryLength: str = ""
    notesPrompt: str = ""
    emailFetchDays: str = ""


@router.get("")
async def get_config():
    return settings_store.public_settings(await settings_store.load_settings())


async def get_runtime_config() -> dict:
    """Internal use only: background fetches need the saved credential."""
    return await settings_store.load_settings()


@router.post("")
async def save_config(config: AppConfigModel, _: None = Depends(require_admin)):
    # TikHub credentials can only change via the verified /tikhub/key endpoint.
    await settings_store.save_settings(config.model_dump())
    return {"status": "success", **settings_store.public_settings(await settings_store.load_settings())}
