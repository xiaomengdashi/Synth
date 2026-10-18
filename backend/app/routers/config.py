import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.services import settings_store
from app.services.fetch_priorities import SETTINGS_KEY, priority_view, resolve_priorities, validate_priorities
from app.services.twitter_cli_settings import twitter_cli_config_view, twitter_cli_updates

from app.routers.admin_auth import require_admin
from app.timezones import server_time_zone

router = APIRouter()


@router.get('/timezone')
async def get_server_timezone():
    return {'timeZone': server_time_zone()}


class FetchPrioritiesModel(BaseModel):
    priorities: dict[str, list[str]]


@router.get("/twitter-cli")
async def get_twitter_cli_config(_: None = Depends(require_admin)):
    return twitter_cli_config_view(await settings_store.load_settings())


@router.post("/twitter-cli/verify")
async def verify_twitter_cli_config(_: None = Depends(require_admin)):
    from app.services.fetchers.x_twitter_cli import verify_twitter_cli
    return await verify_twitter_cli(await settings_store.load_settings())


@router.put("/twitter-cli")
async def save_twitter_cli_config(request: Request, _: None = Depends(require_admin)):
    # Validate manually so FastAPI's validation errors cannot echo cookie inputs.
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='配置必须是 JSON 对象。') from exc
    try:
        updates = twitter_cli_updates(payload, await settings_store.load_settings())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await settings_store.save_settings(updates)
    return twitter_cli_config_view(await settings_store.load_settings())


@router.delete("/twitter-cli")
async def clear_twitter_cli_credentials(_: None = Depends(require_admin)):
    await settings_store.save_settings({'twitterAuthToken': '', 'twitterCt0': ''})
    return twitter_cli_config_view(await settings_store.load_settings())


@router.get("/fetch-priorities")
async def get_fetch_priorities(_: None = Depends(require_admin)):
    return priority_view(await settings_store.load_settings())


@router.put("/fetch-priorities")
async def save_fetch_priorities(data: FetchPrioritiesModel, _: None = Depends(require_admin)):
    try:
        validate_priorities(data.priorities)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    priorities = resolve_priorities(await settings_store.load_settings())
    priorities.update(data.priorities)
    await settings_store.save_settings({SETTINGS_KEY: json.dumps(priorities)})
    return priority_view(await settings_store.load_settings())


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
async def get_config(_: None = Depends(require_admin)):
    # 配置含邮箱账号、代理地址等隐私字段,密钥虽已脱敏仍不对外公开
    return settings_store.public_settings(await settings_store.load_settings())


async def get_runtime_config() -> dict:
    """Internal use only: background fetches need the saved credential."""
    return await settings_store.load_settings()


@router.post("")
async def save_config(config: AppConfigModel, _: None = Depends(require_admin)):
    # TikHub credentials can only change via the verified /tikhub/key endpoint.
    await settings_store.save_settings(config.model_dump())
    return {"status": "success", **settings_store.public_settings(await settings_store.load_settings())}
