"""应用配置存取（SQLite app_settings 表，取代旧的 data/config.json）。

配置是服务端状态：任务处理链路从这里读取（含 TikHub Token），
前端只通过配置接口提交更新，不再把配置随任务回传。
密钥类配置（TikHub Token）只能通过验证专用接口写入。
"""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import AsyncSessionLocal
from app.models import AppSetting

SUPPORTED_KEYS = ("apiKey", "baseUrl", "modelName", "tikhubApiKey")


async def load_settings() -> dict[str, str]:
    """读取全部支持的配置项（缺省为空字符串）。"""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(AppSetting).where(AppSetting.key.in_(SUPPORTED_KEYS)))
        stored = {row.key: row.value for row in rows.scalars()}
    return {key: stored.get(key, "") for key in SUPPORTED_KEYS}


async def save_settings(values: dict) -> dict[str, str]:
    """按 key upsert。出现的键全部写入（空字符串表示清空）；掩码回传跳过。"""
    written: dict[str, str] = {}
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        for key in SUPPORTED_KEYS:
            if key not in values:
                continue
            value = str(values.get(key) or "").strip()
            if is_masked(value):
                continue
            statement = sqlite_insert(AppSetting).values(key=key, value=value, updated_at=now)
            statement = statement.on_conflict_do_update(
                index_elements=[AppSetting.key],
                set_={"value": statement.excluded.value, "updated_at": statement.excluded.updated_at},
            )
            await session.execute(statement)
            written[key] = value
        await session.commit()
    return written


def mask_secret(value: str) -> str:
    """敏感值脱敏展示：只保留末 4 位。"""
    value = str(value or "").strip()
    return f"••••{value[-4:]}" if len(value) > 8 else ("••••" if value else "")


def is_masked(value: str) -> bool:
    """识别掩码回传（•••• 开头），保存时跳过。"""
    value = str(value or "").strip()
    return value.startswith("••••")


def key_metadata(values: dict) -> dict:
    """TikHub Key 的公开元数据（不含密钥本体）。"""
    stored = str(values.get("tikhubApiKey") or "").strip()
    return {
        "configured": bool(stored),
        "source": "config" if stored else None,
        "masked_key": mask_secret(stored),
        "has_saved_key": bool(stored),
    }


def public_settings(values: dict) -> dict:
    """给前端的配置视图：密钥仅返回掩码，不返回数据库中的原文。"""
    model_key = str(values.get("apiKey") or "").strip()
    return {
        "apiKey": mask_secret(model_key),
        "apiKeyConfigured": bool(model_key),
        "baseUrl": str(values.get("baseUrl") or ""),
        "modelName": str(values.get("modelName") or ""),
        "tikhubConfigured": key_metadata(values)["configured"],
    }
