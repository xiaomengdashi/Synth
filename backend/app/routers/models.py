"""模型服务连通性：拉取 OpenAI 兼容的可用模型列表、测试当前参数是否可用。

请求体中的 baseUrl/apiKey/model 均可选，缺省（或回传掩码）时使用已保存配置；
这样「测试连接」既能测表单里的新参数，也能测已保存的参数。
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import settings_store

router = APIRouter()


class ModelCredentials(BaseModel):
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""


def _is_masked(value: str) -> bool:
    return "•" in value or "..." in value


async def _effective(payload: ModelCredentials) -> tuple[str, str, str]:
    saved = await settings_store.load_settings()
    base = (payload.baseUrl or "").strip() or saved.get("baseUrl", "")
    key = (payload.apiKey or "").strip()
    if not key or _is_masked(key):
        key = saved.get("apiKey", "")
    model = (payload.model or "").strip() or saved.get("modelName", "")
    return base, key, model


def _candidate_bases(base: str) -> list[str]:
    """Base URL 常见两种写法：带 /v1 与不带。不带时优先按 OpenAI 惯例补 /v1，再试原样。"""
    base = base.strip().rstrip("/")
    if base.endswith("/v1"):
        return [base]
    return [f"{base}/v1", base]


def _error_detail(status: int, body: str) -> str:
    snippet = " ".join((body or "").split())[:200]
    return f"HTTP {status}{f'：{snippet}' if snippet else ''}"


@router.post("/list")
async def list_models(payload: ModelCredentials):
    base, key, _ = await _effective(payload)
    if not base:
        raise HTTPException(400, "请先填写 Base URL。")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    last_error = "未知错误"
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for candidate in _candidate_bases(base):
            try:
                resp = await client.get(f"{candidate}/models", headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"连接失败（{exc.__class__.__name__}）"
                continue
            if resp.status_code == 404:
                last_error = _error_detail(404, "")
                continue
            if resp.status_code != 200:
                raise HTTPException(502, f"模型服务返回错误：{_error_detail(resp.status_code, resp.text)}")
            try:
                data = resp.json().get("data") or []
            except ValueError:
                last_error = "服务返回了无法解析的响应"
                continue
            models = sorted({str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")})
            return {"models": models}
    raise HTTPException(502, f"获取模型列表失败：{last_error}。请检查 Base URL（例如 https://api.openai.com/v1）。")


@router.post("/test")
async def test_model(payload: ModelCredentials):
    base, key, model = await _effective(payload)
    if not base:
        raise HTTPException(400, "请先填写 Base URL。")
    if not key:
        raise HTTPException(400, "请先填写 API Key。")
    if not model:
        raise HTTPException(400, "请先选择模型。")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    started = time.perf_counter()
    last_error = "未知错误"
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        for candidate in _candidate_bases(base):
            try:
                resp = await client.post(f"{candidate}/chat/completions", headers=headers, json=body)
            except httpx.HTTPError as exc:
                last_error = f"连接失败（{exc.__class__.__name__}）"
                continue
            if resp.status_code == 404:
                last_error = _error_detail(404, resp.text)
                continue
            latency_ms = int((time.perf_counter() - started) * 1000)
            if resp.status_code == 200:
                return {"ok": True, "latency_ms": latency_ms}
            if resp.status_code in (401, 403):
                raise HTTPException(502, f"认证失败（{_error_detail(resp.status_code, resp.text)}）：请检查 API Key 是否有效。")
            raise HTTPException(502, f"模型服务返回错误：{_error_detail(resp.status_code, resp.text)}")
    raise HTTPException(502, f"连接失败：{last_error}。请检查 Base URL 与网络。")
