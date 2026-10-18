"""应用配置存取（SQLite app_settings 表，取代旧的 data/config.json）。

配置是服务端状态：任务处理链路从这里读取（含 TikHub Token），
前端只通过配置接口提交更新，不再把配置随任务回传。
密钥类配置（TikHub Token）只能通过验证专用接口写入。
"""

from __future__ import annotations

import datetime
import hashlib
import hmac

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import AsyncSessionLocal
from app.models import AppSetting

SUPPORTED_KEYS = (
    "apiKey", "baseUrl", "modelName", "tikhubApiKey", "minimaxApiKey",
    "imapHost", "imapUser", "imapPassword", "imapSenderWhitelist",
    "tikhubApiBase", "bilibiliProxy", "minimaxApiBase",
    "llmTemperature", "llmMaxTokens", "llmTimeoutSeconds",
    "summaryLength", "notesPrompt", "emailFetchDays",
    "fetchProviderPriorities",
    "twitterAuthToken", "twitterCt0", "twitterCliBin",
)

# 可调参数的出厂默认：库中未存或存空时按此回填，后台留空即恢复默认行为。
# minimaxApiBase / bilibiliProxy 刻意不设默认（同 imapHost 模式）：
# 留空即"用官方地址/直连"，仅自定义时才填写。
SETTING_DEFAULTS = {
    "tikhubApiBase": "https://api.tikhub.io",
    "llmTemperature": "0.3",
    "llmMaxTokens": "512000",
    "llmTimeoutSeconds": "300",
    "summaryLength": "120",
    "notesPrompt": "",
    "emailFetchDays": "7",
}


async def load_settings() -> dict[str, str]:
    """读取全部支持的配置项（凭据类缺省为空字符串，可调参数缺省回填默认值）。"""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(AppSetting).where(AppSetting.key.in_(SUPPORTED_KEYS)))
        stored = {row.key: row.value for row in rows.scalars()}
    values = {key: stored.get(key, "") for key in SUPPORTED_KEYS}
    for key, default in SETTING_DEFAULTS.items():
        if not values.get(key, "").strip():
            values[key] = default
    return values


def numeric_setting(
    values: dict,
    key: str,
    default: float,
    *,
    lo: float | None = None,
    hi: float | None = None,
    integer: bool = False,
) -> float | int:
    """解析数值型配置：空值/非法值回默认，并夹到 [lo, hi] 区间。"""
    raw = str((values or {}).get(key) or "").strip()
    try:
        number: float = float(raw)
    except ValueError:
        number = default
    if integer:
        number = float(int(number))
    if lo is not None:
        number = max(lo, number)
    if hi is not None:
        number = min(hi, number)
    return int(number) if integer else number


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
    minimax_key = str(values.get("minimaxApiKey") or "").strip()
    imap_user = str(values.get("imapUser") or "").strip()
    imap_password = str(values.get("imapPassword") or "").strip()
    return {
        "apiKey": mask_secret(model_key),
        "apiKeyConfigured": bool(model_key),
        "baseUrl": str(values.get("baseUrl") or ""),
        "modelName": str(values.get("modelName") or ""),
        "tikhubConfigured": key_metadata(values)["configured"],
        "minimaxApiKey": mask_secret(minimax_key),
        "minimaxConfigured": bool(minimax_key),
        "imapHost": str(values.get("imapHost") or ""),
        "imapUser": imap_user,
        "imapPassword": mask_secret(imap_password),
        "imapSenderWhitelist": str(values.get("imapSenderWhitelist") or ""),
        "imapConfigured": bool(imap_user and imap_password),
        # 可调参数非敏感，明文回显（load_settings 已回填默认值）
        "tikhubApiBase": str(values.get("tikhubApiBase") or ""),
        "bilibiliProxy": str(values.get("bilibiliProxy") or ""),
        "minimaxApiBase": str(values.get("minimaxApiBase") or ""),
        "llmTemperature": str(values.get("llmTemperature") or ""),
        "llmMaxTokens": str(values.get("llmMaxTokens") or ""),
        "llmTimeoutSeconds": str(values.get("llmTimeoutSeconds") or ""),
        "summaryLength": str(values.get("summaryLength") or ""),
        "notesPrompt": str(values.get("notesPrompt") or ""),
        "emailFetchDays": str(values.get("emailFetchDays") or ""),
    }


CATEGORY_SETTINGS_KEY = "categories"


async def load_categories() -> list[str]:
    """分类列表存于 app_settings(JSON 数组文本),供前台菜单与后台管理共用。"""
    import json as _json

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(AppSetting).where(AppSetting.key == CATEGORY_SETTINGS_KEY)
        )
        stored = row.scalar_one_or_none()
    if not stored or not stored.value:
        return []
    try:
        names = _json.loads(stored.value)
    except ValueError:
        return []
    return [str(name).strip() for name in names if str(name).strip()]


async def save_categories(names: list[str]) -> list[str]:
    """整体保存分类列表:去空、去重、保序。"""
    import json as _json
    import datetime as _dt

    cleaned: list[str] = []
    for name in names:
        value = str(name).strip()
        if value and value not in cleaned:
            cleaned.append(value)

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(AppSetting).where(AppSetting.key == CATEGORY_SETTINGS_KEY)
        )
        stored = row.scalar_one_or_none()
        if stored is None:
            stored = AppSetting(key=CATEGORY_SETTINGS_KEY, value=_json.dumps(cleaned, ensure_ascii=False))
            session.add(stored)
        else:
            stored.value = _json.dumps(cleaned, ensure_ascii=False)
            stored.updated_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
        await session.commit()
    return cleaned


ADMIN_TOKEN_KEY = "admin_token_hash"


def hash_admin_token(token: str) -> str:
    """单向哈希存储:数据库中不落令牌原文。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_admin_token_hash() -> str:
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(AppSetting).where(AppSetting.key == ADMIN_TOKEN_KEY)
        )
        stored = row.scalar_one_or_none()
    return (stored.value or "") if stored else ""


async def set_admin_token_hash(value: str) -> None:
    import datetime as _dt

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(AppSetting).where(AppSetting.key == ADMIN_TOKEN_KEY)
        )
        stored = row.scalar_one_or_none()
        if stored is None:
            stored = AppSetting(key=ADMIN_TOKEN_KEY, value=value)
            session.add(stored)
        else:
            stored.value = value
            stored.updated_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
        await session.commit()


async def verify_admin_token(token: str) -> bool:
    stored = await get_admin_token_hash()
    if not stored:
        return False  # 未初始化:由依赖层决定放行(首次设置流程)
    return hmac.compare_digest(hash_admin_token(token or ""), stored)


EMAIL_PROCESSED_KEY = "emailProcessedMessageIds"
EMAIL_PROCESSED_CAP = 500


async def load_processed_message_ids() -> list[str]:
    """已入库邮件的 Message-ID 清单(JSON 数组),用于拉取去重。"""
    import json as _json

    async with AsyncSessionLocal() as session:
        row = await session.execute(select(AppSetting).where(AppSetting.key == EMAIL_PROCESSED_KEY))
        stored = row.scalar_one_or_none()
    if not stored or not stored.value:
        return []
    try:
        ids = _json.loads(stored.value)
    except ValueError:
        return []
    return [str(item) for item in ids if str(item)]


async def record_processed_message_ids(new_ids: list[str]) -> list[str]:
    """合并新入库的 Message-ID,去重后 FIFO 保留最近 EMAIL_PROCESSED_CAP 条。"""
    import datetime as _dt
    import json as _json

    incoming = [str(item).strip() for item in new_ids if str(item).strip()]
    merged = [item for item in await load_processed_message_ids() if item not in set(incoming)]
    seen: set[str] = set()
    merged = [item for item in merged + incoming if not (item in seen or seen.add(item))]
    kept = merged[-EMAIL_PROCESSED_CAP:]

    async with AsyncSessionLocal() as session:
        row = await session.execute(select(AppSetting).where(AppSetting.key == EMAIL_PROCESSED_KEY))
        stored = row.scalar_one_or_none()
        payload = _json.dumps(kept, ensure_ascii=False)
        if stored is None:
            session.add(AppSetting(key=EMAIL_PROCESSED_KEY, value=payload))
        else:
            stored.value = payload
            stored.updated_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
        await session.commit()
    return kept
