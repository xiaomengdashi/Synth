"""后台访问令牌:首次设置、登录校验、修改令牌与管理接口鉴权依赖。"""

import time
from collections import deque

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.settings_store import (
    get_admin_token_hash,
    hash_admin_token,
    set_admin_token_hash,
    verify_admin_token,
)

router = APIRouter()

# 登录/改令牌的 IP 限速:窗口内连续失败 N 次即暂时拒绝,防在线爆破。
# 内存态即可——单进程部署,重启清零是可接受的放宽。
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = 60.0
_login_failures: dict[str, deque[float]] = {}
_now = time.monotonic  # 测试注入用


def _client_ip(request: Request) -> str:
    # 线上 nginx 的 proxy_set_header X-Real-IP $remote_addr 会覆盖客户端伪造值,可信任;
    # 直连(本地开发)时无此头,退回 socket 地址。
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _too_many_attempts(ip: str) -> bool:
    attempts = _login_failures.get(ip)
    if not attempts:
        return False
    now = _now()
    while attempts and attempts[0] <= now - LOGIN_RATE_WINDOW:
        attempts.popleft()
    return len(attempts) >= LOGIN_RATE_LIMIT


def _record_failure(ip: str) -> None:
    _login_failures.setdefault(ip, deque()).append(_now())


def _clear_failures(ip: str) -> None:
    _login_failures.pop(ip, None)


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
async def login_token(payload: TokenLoginPayload, request: Request):
    ip = _client_ip(request)
    if _too_many_attempts(ip):
        raise HTTPException(status_code=429, detail="尝试过于频繁，请 1 分钟后再试")
    if not await verify_admin_token(payload.token):
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="访问令牌不正确")
    _clear_failures(ip)
    return {"ok": True}


@router.put("/token")
async def change_token(payload: TokenChangePayload, request: Request):
    ip = _client_ip(request)
    if _too_many_attempts(ip):
        raise HTTPException(status_code=429, detail="尝试过于频繁，请 1 分钟后再试")
    if not await verify_admin_token(payload.current):
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="当前令牌不正确")
    await set_admin_token_hash(hash_admin_token(payload.next))
    _clear_failures(ip)
    return {"ok": True}


async def require_admin(x_admin_token: str = Header(default="")):
    """管理类写接口的鉴权依赖。未初始化(首次部署尚未设置令牌)时放行，由前端引导完成初始化。"""
    if not await get_admin_token_hash():
        return
    if not await verify_admin_token(x_admin_token):
        raise HTTPException(status_code=401, detail="需要有效的后台访问令牌")
