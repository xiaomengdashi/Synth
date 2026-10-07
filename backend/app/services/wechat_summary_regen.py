"""存量微信文章摘要批量重生成：用大模型浓缩正文，替换旧的本地截取摘要。

后台接口（线程跑批 + 进度轮询）与服务器 CLI 共用 regenerate_wechat_summaries。
逐篇调用 LLM，失败或正文过短时保留原摘要（幂等，可随时重跑）。
"""

from __future__ import annotations

import datetime
import re

from bs4 import BeautifulSoup
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Article
from app.services.article_summary import MIN_INPUT_CHARS, generate_article_summary
from app.services.runtime_store import ARTICLES_DB
from app.services.settings_store import load_settings, numeric_setting

# content_md 开头的摘要段：## 内容摘要\n\n<旧摘要>\n\n--- 后面是原文
_SUMMARY_SECTION_RE = re.compile(r"^(## 内容摘要\n\n)(.*?)(\n\n---)", re.DOTALL)
_HTML_BLOCK_RE = re.compile(
    r"<!-- HTML_CONTENT_START -->\n?(.*?)\n?<!-- HTML_CONTENT_END -->", re.DOTALL
)
_MD_BODY_SPLIT_RE = re.compile(r"^## 内容摘要\n\n.*?\n\n---\n\n", re.DOTALL)

BATCH_SIZE = 50


def extract_body_text(content_md: str) -> str:
    """从存量 content_md 还原供摘要用的纯文本：优先 HTML 复刻块，其次 markdown 正文。"""
    text = str(content_md or "")
    match = _HTML_BLOCK_RE.search(text)
    if match:
        return BeautifulSoup(match.group(1), "html.parser").get_text("\n", strip=True)
    return _MD_BODY_SPLIT_RE.sub("", text, count=1).strip()


def replace_summary_section(content_md: str, new_summary: str) -> str:
    """替换 content_md 开头的摘要段；结构不匹配时原样返回（调用方只更新 summary 字段）。"""
    if _SUMMARY_SECTION_RE.search(content_md):
        return _SUMMARY_SECTION_RE.sub(
            lambda m: m.group(1) + new_summary + m.group(3), content_md, count=1
        )
    return content_md


# 模块级进度：重启丢失但重跑幂等；running 期间拒绝重复启动
_progress: dict = {"running": False, "total": 0, "done": 0, "ok": 0, "skipped": 0, "failed": 0, "current": ""}


def progress_snapshot() -> dict:
    return {**_progress}


async def regenerate_wechat_summaries() -> dict:
    """遍历全部微信文章逐篇重生成摘要，返回最终统计。"""
    if _progress.get("running"):
        return progress_snapshot()
    config = await load_settings()
    summary_limit = int(numeric_setting(config, "summaryLength", 120, lo=20, hi=2000, integer=True))

    _progress.update(running=True, total=0, done=0, ok=0, skipped=0, failed=0, current="")

    # 先取全部 id 再分批取文章，避免长事务
    async with AsyncSessionLocal() as session:
        ids = (
            await session.execute(
                select(Article.id).where(Article.source_type == "wechat").order_by(Article.created_at.asc())
            )
        ).scalars().all()
    _progress["total"] = len(ids)

    for offset in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[offset : offset + BATCH_SIZE]
        async with AsyncSessionLocal() as session:
            articles = (
                await session.execute(select(Article).where(Article.id.in_(batch_ids)))
            ).scalars().all()
            for article in articles:
                _progress["current"] = article.title[:60]
                body = extract_body_text(article.content_md)
                if len(body) < MIN_INPUT_CHARS:
                    # 图片消息等过短正文：不值得一次模型调用，保留原摘要
                    _progress["skipped"] += 1
                    _progress["done"] += 1
                    continue
                try:
                    summary = await generate_article_summary(
                        article.title, body, config, limit=summary_limit
                    )
                except Exception:
                    _progress["failed"] += 1
                    _progress["done"] += 1
                    continue
                article.summary = summary
                article.content_md = replace_summary_section(article.content_md, summary)
                article.updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                if article.id in ARTICLES_DB:
                    ARTICLES_DB[article.id]["summary"] = summary
                    ARTICLES_DB[article.id]["content_md"] = article.content_md
                _progress["ok"] += 1
                _progress["done"] += 1
            # 每批一个事务：中断时已处理的批次保留成果
            await session.commit()

    _progress.update(running=False, current="")
    return progress_snapshot()
