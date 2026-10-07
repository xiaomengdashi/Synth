"""TikHub credentials, account summary, and read-only multi-platform queries."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import settings_store
from app.services.fetchers.tikhub import (
    TikHubError, TikHubNotConfiguredError, fetch_tikhub_account,
    resolve_tikhub_base, resolve_tikhub_token, verify_tikhub_token,
)
from app.services.tikhub_queries import query_catalog, run_query, safe_response

router = APIRouter()


class TikHubKeyPayload(BaseModel):
    apiKey: str = Field(max_length=4096)


class TikHubQueryPayload(BaseModel):
    endpoint_id: str = Field(max_length=300)
    parameters: dict = Field(default_factory=dict)


async def _token() -> str:
    try:
        return resolve_tikhub_token(await settings_store.load_settings())
    except TikHubNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail='请先设置 TikHub API Key。') from exc


@router.get('/key')
async def get_tikhub_key():
    return settings_store.key_metadata(await settings_store.load_settings())


@router.post('/key')
async def set_tikhub_key(data: TikHubKeyPayload):
    token = data.apiKey.strip()
    if not token or any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in token):
        raise HTTPException(status_code=400, detail='API Token 不能为空，也不能包含空格或非 ASCII 字符。')
    # 验证走已保存的 API 端点；先保存端点再粘贴 Key
    resolve_tikhub_base(await settings_store.load_settings())
    try:
        summary = await asyncio.to_thread(verify_tikhub_token, token)
    except TikHubError as exc:
        raise HTTPException(status_code=400, detail=f'Token 验证失败：{exc}') from exc
    # 验证通过才写入 SQLite
    await settings_store.save_settings({'tikhubApiKey': token})
    return {'status': 'success', 'message': 'Token 验证通过并已保存。',
            **settings_store.key_metadata(await settings_store.load_settings()), 'account': safe_response(summary, token)}


@router.delete('/key')
async def delete_tikhub_key():
    await settings_store.save_settings({'tikhubApiKey': ''})
    return settings_store.key_metadata(await settings_store.load_settings())


@router.get('/account')
async def get_tikhub_account():
    metadata = settings_store.key_metadata(await settings_store.load_settings())
    if not metadata['configured']:
        return {'configured': False}
    token = await _token()
    try:
        # 传完整配置：fetch_tikhub_account 内部按配置端点刷新后再取账户
        account = await asyncio.to_thread(
            fetch_tikhub_account, {**await settings_store.load_settings(), 'tikhubApiKey': token})
    except TikHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {**metadata, **safe_response(account, token), 'updated_at': datetime.now(timezone.utc).isoformat()}


@router.get('/catalog')
async def get_catalog(platform: str = '', q: str = Query('', max_length=200),
                      offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    return query_catalog(platform, q, offset, limit)


@router.post('/query')
async def query_tikhub(data: TikHubQueryPayload):
    token = await _token()
    try:
        result = await asyncio.to_thread(run_query, data.endpoint_id, data.parameters, token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TikHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {**result, 'queried_at': datetime.now(timezone.utc).isoformat()}
