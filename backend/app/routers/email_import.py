"""后台邮箱导入：163 IMAP 拉取白名单发件人的 .md 附件,入库为 B 站来源文章。

入库/去重在路由层完成,与 import-html 先例一致;
去重靠 Message-ID(app_settings 内部 key),邮箱侧零状态写入。
"""

import asyncio
import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.database import AsyncSessionLocal
from app.models import Article
from app.routers.admin_auth import require_admin
from app.services import settings_store
from app.services.email_client import (
    EmailAuthError,
    EmailFetchError,
    EmailMessageData,
    extract_bilibili_url,
    fetch_whitelisted_messages,
    title_from_markdown,
)
from app.services.runtime_store import ARTICLES_DB

router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _import_articles_for_message(message: EmailMessageData) -> list[dict]:
    """一个 md 附件一篇 Article;同一事务提交,失败则整封重试。"""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    imported: list[dict] = []
    async with AsyncSessionLocal() as session:
        for attachment in message.md_attachments:
            title = title_from_markdown(attachment["content"], message.subject, attachment["filename"])
            article_id = str(uuid.uuid4())
            article_data = {
                "id": article_id,
                "title": title,
                "summary": "",
                "content_md": attachment["content"],
                "original_url": extract_bilibili_url(attachment["content"]),
                "source_type": "bilibili",
                "cover_image_url": "",
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
                original_url=article_data["original_url"],
                source_type="bilibili",
                cover_image_url="",
                account_name=message.from_addr,
                publish_time=message.date,
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
    imported: list[dict] = []
    skipped: list[dict] = []
    newly_done: list[str] = []
    for message in messages:
        if not message.md_attachments:
            skipped.append({"subject": message.subject, "reason": "邮件没有 .md 附件"})
            continue
        if message.message_id in processed:
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
