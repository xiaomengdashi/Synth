"""后台邮箱导入：163 IMAP 拉取白名单发件人的 .md 附件,入库为 B 站来源文章。

入库/去重在路由层完成,与 import-html 先例一致;
去重靠 Message-ID(app_settings 内部 key),邮箱侧零状态写入。
"""

import asyncio
import datetime
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Article
from app.routers.admin_auth import require_admin
from app.services import settings_store
from app.services.email_client import (
    EmailAuthError,
    EmailFetchError,
    EmailMessageData,
    extract_bilibili_reference,
    fetch_whitelisted_messages,
    title_from_markdown,
)
from app.services.fetchers.tikhub import _extract_bilibili_bvid, _resolve_b23_short_url
from app.services.fetchers.video import _fetch_bilibili_official_view, _localize_bilibili_cover
from app.services.runtime_store import ARTICLES_DB

router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _placeholder_cover_svg(title: str, article_id: str) -> str:
    """本地生成 SVG 占位封面:外链生图服务(trae.ai)国内直连不可达,封面必须本地化。"""
    safe = (title or "笔记")[:14].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#175B41"/><stop offset="1" stop-color="#2E8B63"/></linearGradient></defs>'
        '<rect width="640" height="360" fill="url(#g)"/>'
        f'<text x="40" y="196" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="34" fill="#F5F1E8">{safe}</text>'
        "</svg>"
    )
    target_dir = settings.MEDIA_DIR.rstrip("/") + "/covers"
    os.makedirs(target_dir, exist_ok=True)
    with open(f"{target_dir}/{article_id}.svg", "w", encoding="utf-8") as fh:
        fh.write(svg)
    return f"/media/covers/{article_id}.svg"


def _resolve_cover_for_article(reference: str, title: str, article_id: str) -> str:
    """B站引用→官方真实封面并本地化;无引用或失败→本地 SVG 占位(不依赖任何外链)。"""
    if reference:
        try:
            url = reference if reference.startswith("http") else f"https://www.bilibili.com/video/{reference}"
            bvid = _extract_bilibili_bvid(_resolve_b23_short_url(url))
            view = _fetch_bilibili_official_view(bvid)
            pic = str(view.get("pic") or "")
            if pic:
                localized = _localize_bilibili_cover(pic, bvid)
                if localized:
                    return localized
        except Exception:
            pass  # 封面是增强,任何失败都回退本地占位,不阻断入库
    return _placeholder_cover_svg(title, article_id)


async def _import_articles_for_message(message: EmailMessageData) -> list[dict]:
    """一个 md 附件一篇 Article;同一事务提交,失败则整封重试。"""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    imported: list[dict] = []
    async with AsyncSessionLocal() as session:
        for attachment in message.md_attachments:
            title = title_from_markdown(attachment["content"], message.subject, attachment["filename"])
            reference = extract_bilibili_reference(attachment["content"], message.subject)
            if reference.startswith("http"):
                original_url = reference
            else:
                original_url = f"https://www.bilibili.com/video/{reference}" if reference else ""
            article_id = str(uuid.uuid4())
            cover_image_url = await asyncio.to_thread(
                _resolve_cover_for_article, reference, title, article_id
            )
            article_data = {
                "id": article_id,
                "title": title,
                "summary": "",
                "content_md": attachment["content"],
                "original_url": original_url,
                "source_type": "bilibili",
                "cover_image_url": cover_image_url,
                "account_name": message.from_addr,
                "publish_time": message.date,
                "created_at": now.isoformat(),
            }
            ARTICLES_DB[article_id] = article_data
            session.add(Article(
                id=article_id,
                title=title,
                summary="",
                content_md=attachment["content"],
                original_url=original_url,
                source_type="bilibili",
                cover_image_url=cover_image_url,
                account_name=message.from_addr,
                publish_time=message.date,
                email_message_id=message.message_id,
                created_at=now,
            ))
            imported.append({"id": article_id, "title": title, "filename": attachment["filename"]})
        await session.commit()
    return imported


@router.post("/test")
async def test_email_connection(_: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config)
    except (EmailAuthError, EmailFetchError) as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "recent_count": len(messages)}


@router.post("/fetch")
async def fetch_email_articles(_: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config)
    except (EmailAuthError, EmailFetchError) as exc:
        raise _http_error(exc) from exc

    processed = set(await settings_store.load_processed_message_ids())
    # 去重以「文章还在不在」为准:清单命中但文章已删的,重拉放行重新导入
    live_ids: set[str] = set()
    if processed:
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(Article.email_message_id).where(Article.email_message_id.in_(processed))
            )
            live_ids = {row[0] for row in rows if row[0]}
    imported: list[dict] = []
    skipped: list[dict] = []
    newly_done: list[str] = []
    for message in messages:
        if not message.md_attachments:
            skipped.append({"subject": message.subject, "reason": "邮件没有 .md 附件"})
            continue
        if message.message_id in processed and message.message_id in live_ids:
            skipped.append({"subject": message.subject, "reason": "已导入过，跳过"})
            continue
        try:
            imported.extend(await _import_articles_for_message(message))
        except Exception:
            skipped.append({"subject": message.subject, "reason": "入库失败，下次拉取会重试"})
            continue
        newly_done.append(message.message_id)
    if newly_done:
        await settings_store.record_processed_message_ids(newly_done)
    return {"fetched": len(messages), "imported": imported, "skipped": skipped}
