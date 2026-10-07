"""微信文章 LLM 摘要：prompt 组装、围栏清理、过短跳过与回退链路。"""

import asyncio

from app.services import task_service
from app.services.article_summary import (
    ArticleSummarySkipped,
    generate_article_summary,
)


def test_generate_article_summary_strips_fence_and_builds_prompt(monkeypatch):
    captured: dict = {}

    async def fake_chat(messages, config=None, **kwargs):
        captured["messages"] = messages
        return "```\n这是模型生成的摘要。\n```"

    monkeypatch.setattr("app.services.article_summary.chat_completion", fake_chat)
    body = "微信正文内容。" * 50
    result = asyncio.run(generate_article_summary("文章标题", body, {"baseUrl": "x"}, limit=88))
    assert result == "这是模型生成的摘要。"

    prompt = captured["messages"][1]["content"]
    assert "文章标题" in prompt
    assert "微信正文内容" in prompt
    assert "88" in prompt  # 摘要长度要求进了 prompt


def test_generate_article_summary_truncates_long_input(monkeypatch):
    captured: dict = {}

    async def fake_chat(messages, config=None, **kwargs):
        captured["prompt"] = messages[1]["content"]
        return "摘要"

    monkeypatch.setattr("app.services.article_summary.chat_completion", fake_chat)
    from app.services.article_summary import MAX_INPUT_CHARS
    body = "字" * (MAX_INPUT_CHARS + 5000)
    asyncio.run(generate_article_summary("标题", body, None))
    assert "字" * MAX_INPUT_CHARS in captured["prompt"]
    assert len(captured["prompt"]) < MAX_INPUT_CHARS + 2000


def test_generate_article_summary_skips_short_body():
    try:
        asyncio.run(generate_article_summary("标题", "太短", None))
    except ArticleSummarySkipped:
        pass
    else:
        raise AssertionError("expected ArticleSummarySkipped for short body")


def test_resolve_summary_uses_llm_for_wechat_and_falls_back(monkeypatch):
    payload = {"title": "微信文章", "extracted_md": "正文" * 100}
    step_calls: list[str] = []

    async def fake_llm_ok(title, body, config, *, limit=120):
        return f"LLM 摘要（{limit} 字目标）"

    monkeypatch.setattr(task_service, "generate_article_summary", fake_llm_ok)
    summary = asyncio.run(task_service.resolve_article_summary(
        "https://mp.weixin.qq.com/s/abc", payload, {}, 120, step_calls.append))
    assert summary.startswith("LLM 摘要")
    assert any("大模型" in step for step in step_calls)

    # LLM 失败 → 回退本地截取，不抛异常
    async def fake_llm_fail(*args, **kwargs):
        raise RuntimeError("模型服务未配置完整")

    monkeypatch.setattr(task_service, "generate_article_summary", fake_llm_fail)
    step_calls.clear()
    summary = asyncio.run(task_service.resolve_article_summary(
        "https://mp.weixin.qq.com/s/abc", payload, {}, 120, step_calls.append))
    assert summary.startswith("正文正文")
    assert any("回退" in step for step in step_calls)

    # 非微信来源不调 LLM
    monkeypatch.setattr(task_service, "generate_article_summary", fake_llm_ok)
    step_calls.clear()
    summary = asyncio.run(task_service.resolve_article_summary(
        "https://blog.example.com/post", payload, {}, 120, step_calls.append))
    assert summary.startswith("正文正文") and not step_calls
