from fastapi import APIRouter
from pydantic import BaseModel

from app.services import settings_store

router = APIRouter()


class AppConfigModel(BaseModel):
    apiKey: str = ""
    baseUrl: str = ""
    modelName: str = ""


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
