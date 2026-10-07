"""文章导入的 LLM 摘要：把正文浓缩成列表页摘要，替代本地截取。

目前用于微信公众号文章（链接提交、手机分享、HTML 手动导入）。
LLM 未配置或调用失败时由调用方回退 build_local_summary，导入不因此失败；
正文过短（图片消息一句话）不值得一次模型调用，同样走本地截取。
"""

from __future__ import annotations

from typing import Any

from app.services.llm_client import chat_completion, strip_code_fence

MAX_INPUT_CHARS = 80_000  # 输入上限：防极端长文爆上下文，微信长文一般远小于此
MIN_INPUT_CHARS = 80  # 低于此长度直接本地截取，省一次模型调用


class ArticleSummarySkipped(RuntimeError):
    """正文过短，无需模型摘要（调用方回退本地截取）。"""


SUMMARY_PROMPT = """把下面这篇文章浓缩成一段摘要，用于内容库列表页展示。

要求：
- 用中文写一段流畅自然的短文，概括文章的核心内容、主要观点或结论；
- 不评论、不夸赞，不添加原文没有的信息，不要「本文」「这篇文章」之类的开头白；
- 长度控制在 {limit} 字以内，直接输出摘要正文。

文章标题：{title}

正文：
{body}
"""


async def generate_article_summary(
    title: str,
    body: str,
    config: Any = None,
    *,
    limit: int = 120,
) -> str:
    """LLM 浓缩正文为短摘要；正文过短抛 ArticleSummarySkipped，
    其余失败（未配置、网关断流等）原样抛出，均由调用方回退本地截取。"""
    text = str(body or "").strip()
    if len(text) < MIN_INPUT_CHARS:
        raise ArticleSummarySkipped("正文过短，无需模型摘要")

    prompt = SUMMARY_PROMPT.format(
        title=str(title or "").strip() or "（无标题）",
        body=text[:MAX_INPUT_CHARS],
        limit=max(1, int(limit)),
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": "你是一名严谨的中文内容编辑，擅长把文章浓缩为忠实的摘要。"},
            {"role": "user", "content": prompt},
        ],
        config,
    )
    summary = strip_code_fence(raw)
    if not summary:
        raise RuntimeError("模型返回了空摘要。")
    return summary
