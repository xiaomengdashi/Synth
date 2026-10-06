"""后台邮箱导入：163 IMAP 拉取白名单发件人的 .md 附件,入库为 B 站来源文章。

入库/去重在路由层完成,与 import-html 先例一致;
去重靠 Message-ID(app_settings 内部 key),邮箱侧零状态写入。
"""

import asyncio
import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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


class EmailWindowPayload(BaseModel):
    """拉取窗口:近 N 天;只影响当次拉取/测试,不持久化。"""
    days: int = Field(default=30, ge=1, le=3650)


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _resolve_cover_for_article(reference: str) -> str:
    """B站引用→官方真实封面并本地化;拿不到就留空,前端走来源色块兜底(禁止占位图)。"""
    if not reference:
        return ""
    try:
        url = reference if reference.startswith("http") else f"https://www.bilibili.com/video/{reference}"
        bvid = _extract_bilibili_bvid(_resolve_b23_short_url(url))
        view = _fetch_bilibili_official_view(bvid)
        pic = str(view.get("pic") or "")
        if pic:
            return _localize_bilibili_cover(pic, bvid)
    except Exception:
        pass  # 封面是增强,任何失败都留空,不阻断入库
    return ""


async def _import_articles_for_message(message: EmailMessageData) -> list[dict]:
    """一个 md 附件一篇 Article;同一事务提交,失败则整封重试。
    created_at 用邮件收件时间——前台列表的排序与相对时间都跟真实收件顺序一致。"""
    try:
        received_at = datetime.datetime.strptime(message.date, "%Y-%m-%d %H:%M")
    except ValueError:
        received_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
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
            cover_image_url = await asyncio.to_thread(_resolve_cover_for_article, reference)
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
                "created_at": received_at.isoformat(),
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
                created_at=received_at,
            ))
            imported.append({"id": article_id, "title": title, "filename": attachment["filename"]})
        await session.commit()
    return imported


@router.post("/test")
async def test_email_connection(payload: EmailWindowPayload | None = None, _: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    days = payload.days if payload else 30
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config, days)
    except (EmailAuthError, EmailFetchError) as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "recent_count": len(messages)}


@router.post("/fetch")
async def fetch_email_articles(payload: EmailWindowPayload | None = None, _: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    days = payload.days if payload else 30
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config, days)
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
