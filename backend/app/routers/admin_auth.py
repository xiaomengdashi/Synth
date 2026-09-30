"""后台访问令牌:首次设置、登录校验、修改令牌与管理接口鉴权依赖。"""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.settings_store import (
    get_admin_token_hash,
    hash_admin_token,
    set_admin_token_hash,
    verify_admin_token,
)

router = APIRouter()


class TokenSetupPayload(BaseModel):
    token: str = Field(min_length=6, max_length=128)


class TokenLoginPayload(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class TokenChangePayload(BaseModel):
    current: str = Field(min_length=1, max_length=128)
    next: str = Field(min_length=6, max_length=128)


@router.get("/status")
async def auth_status():
    return {"initialized": bool(await get_admin_token_hash())}


@router.post("/setup")
async def setup_token(payload: TokenSetupPayload):
    if await get_admin_token_hash():
        raise HTTPException(status_code=403, detail="访问令牌已设置，如需修改请登录后更改")
    await set_admin_token_hash(hash_admin_token(payload.token))
    return {"ok": True}


@router.post("/login")
async def login_token(payload: TokenLoginPayload):
    if not await verify_admin_token(payload.token):
        raise HTTPException(status_code=401, detail="访问令牌不正确")
    return {"ok": True}


@router.put("/token")
async def change_token(payload: TokenChangePayload):
    if not await verify_admin_token(payload.current):
        raise HTTPException(status_code=401, detail="当前令牌不正确")
    await set_admin_token_hash(hash_admin_token(payload.next))
    return {"ok": True}


async def require_admin(x_admin_token: str = Header(default="")):
    """管理类写接口的鉴权依赖。未初始化(首次部署尚未设置令牌)时放行，由前端引导完成初始化。"""
    if not await get_admin_token_hash():
        return
    if not await verify_admin_token(x_admin_token):
        raise HTTPException(status_code=401, detail="需要有效的后台访问令牌")
