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
