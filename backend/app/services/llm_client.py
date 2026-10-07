"""OpenAI 兼容 Chat 调用（baseUrl/apiKey/modelName 存于 app_settings）。

必须走流式：openlux 网关对长时间的非流式请求会直接断开连接（生成超过
约一分钟的请求大概率被掐），流式下 token 持续流动则能稳定跑完。
推理型模型（如 MiniMax-M3）会先流 reasoning_content 再流 content，
这里只取 content。网关偶发中途断流，故带整体重试。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.services.settings_store import numeric_setting


class _RetryableStreamError(RuntimeError):
    """可重试：断流、空响应、404（换候选地址）。"""


class _FatalStreamError(RuntimeError):
    """不可重试：鉴权失败、明确的模型服务错误。"""


def strip_code_fence(text: str) -> str:
    """去掉模型输出偶然裹的 ``` 围栏（生成类调用的通用后处理）。"""
    text = text.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _candidate_bases(base: str) -> list[str]:
    """Base URL 常见两种写法：带 /v1 与不带。不带时优先按 OpenAI 惯例补 /v1，再试原样。"""
    base = base.strip().rstrip("/")
    if base.endswith("/v1"):
        return [base]
    return [f"{base}/v1", base]


async def _stream_once(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    body: dict,
) -> str:
    parts: list[str] = []
    async with client.stream("POST", url, headers=headers, json=body) as response:
        if response.status_code == 404:
            raise _RetryableStreamError(f"HTTP 404（{url}）")
        if response.status_code != 200:
            raw = (await response.aread()).decode("utf-8", "replace")
            snippet = " ".join(raw.split())[:200]
            if response.status_code in (401, 403):
                raise _FatalStreamError(f"认证失败（HTTP {response.status_code}）：{snippet}")
            raise _FatalStreamError(f"模型服务返回 HTTP {response.status_code}：{snippet}")
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if chunk.get("error"):
                raise _FatalStreamError(f"模型服务返回错误：{chunk['error']}")
            choices = chunk.get("choices") or []
            delta = (choices[0].get("delta") or {}) if choices else {}
            piece = delta.get("content")
            if piece:
                parts.append(str(piece))
    text = "".join(parts).strip()
    if not text:
        raise _RetryableStreamError("流式响应没有正文（可能在思考阶段被网关中断）")
    return text


async def chat_completion(
    messages: list[dict],
    config: Any = None,
    *,
    temperature: float | None = None,
    # 显式传参优先；缺省时读后台「模型设置 → 生成参数」（非法/留空回落内置默认）
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> str:
    base = str((config or {}).get("baseUrl") or "").strip()
    api_key = str((config or {}).get("apiKey") or "").strip()
    model = str((config or {}).get("modelName") or "").strip()
    if not (base and api_key and model):
        raise RuntimeError("模型服务未配置完整（Base URL / API Key / 模型名称），请在管理后台「模型设置」填写。")

    if temperature is None:
        temperature = numeric_setting(config or {}, "llmTemperature", 0.3, lo=0.0, hi=2.0)
    if max_tokens is None:
        # 默认对齐 MiniMax-M3 官方目录上限 512K；更换模型时可在后台调整为其上限
        max_tokens = numeric_setting(config or {}, "llmMaxTokens", 512_000, lo=1, hi=2_000_000, integer=True)
    if timeout is None:
        timeout = numeric_setting(config or {}, "llmTimeoutSeconds", 300.0, lo=30, hi=1200)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    # 最多 3 次尝试：候选地址轮一遍后可对首个地址再重试一次（网关断流是随机性的）
    urls = (_candidate_bases(base) + [_candidate_bases(base)[0]])[:3]
    last_error = "未知错误"
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=timeout)) as client:
        for candidate in urls:
            try:
                return await _stream_once(client, f"{candidate}/chat/completions", headers, body)
            except (_RetryableStreamError, httpx.HTTPError) as exc:
                last_error = str(exc)
    raise RuntimeError(f"模型调用失败：{last_error}")
