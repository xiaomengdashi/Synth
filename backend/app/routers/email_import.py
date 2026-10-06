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
from app.services.fetchers.tikhub import (
    BILIBILI_PARTS_PATH,
    _extract_bilibili_bvid,
    _resolve_b23_short_url,
    _tikhub_request,
    resolve_tikhub_token,
)
from app.services.fetchers.video import _fetch_bilibili_official_view, _localize_bilibili_cover
from app.services.runtime_store import ARTICLES_DB

router = APIRouter()


class EmailWindowPayload(BaseModel):
    """拉取窗口:近 N 天;只影响当次拉取/测试,不持久化。"""
    days: int = Field(default=7, ge=1, le=3650)


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _fetch_cover_via_tikhub(bvid: str, config: dict | None) -> str:
    """封面降级源:海外服务器直连 B 站官方接口会被 412 风控,TikHub parts 的 first_frame 同为图床封面。"""
    if not bvid:
        return ""
    try:
        token = resolve_tikhub_token(config or {})
    except Exception:
        return ""
    try:
        data = _tikhub_request(BILIBILI_PARTS_PATH, token, params={"bv_id": bvid})
        parts = data.get("data") or []
        return str((parts[0] or {}).get("first_frame") or "") if parts else ""
    except Exception:
        return ""


def _resolve_cover_for_article(reference: str, config: dict | None = None) -> str:
    """封面三级:B站官方接口→TikHub first_frame→留空(禁止占位图)。"""
    if not reference:
        return ""
    url = reference if reference.startswith("http") else f"https://www.bilibili.com/video/{reference}"
    pic = ""
    bvid = ""
    try:
        bvid = _extract_bilibili_bvid(_resolve_b23_short_url(url))
        view = _fetch_bilibili_official_view(bvid)
        pic = str(view.get("pic") or "")
    except Exception:
        pass
    if not pic:
        try:
            if not bvid:
                bvid = _extract_bilibili_bvid(_resolve_b23_short_url(url))
            pic = _fetch_cover_via_tikhub(bvid, config)
        except Exception:
            pic = ""
    if not pic or not bvid:
        return ""
    try:
        return _localize_bilibili_cover(pic, bvid)
    except Exception:
        return ""


async def _import_articles_for_message(message: EmailMessageData, config: dict | None = None) -> list[dict]:
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
            cover_image_url = await asyncio.to_thread(_resolve_cover_for_article, reference, config)
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
    days = payload.days if payload else 7
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config, days)
    except (EmailAuthError, EmailFetchError) as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "recent_count": len(messages)}


@router.post("/fetch")
async def fetch_email_articles(payload: EmailWindowPayload | None = None, _: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    days = payload.days if payload else 7
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
            imported.extend(await _import_articles_for_message(message, config))
        except Exception:
            skipped.append({"subject": message.subject, "reason": "入库失败，下次拉取会重试"})
            continue
        newly_done.append(message.message_id)
    if newly_done:
        await settings_store.record_processed_message_ids(newly_done)
    return {"fetched": len(messages), "imported": imported, "skipped": skipped}
