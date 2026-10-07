import asyncio
import datetime
import json
import re
import uuid

from app.database import AsyncSessionLocal
from app.models import Article, Task
from app.services.fetchers.article import fetch_article_content
from app.services.fetchers.bilibili_audio import fetch_bilibili_transcript_via_asr
from app.services.fetchers.social import extract_x_article_id
from app.services.fetchers.tikhub import TikHubError, TikHubNotConfiguredError, fetch_tikhub_tweet
from app.services.fetchers.twitter_article_rich import render_twitter_article_result
from app.services.fetchers.x_article import fetch_x_article_replica
from app.services.fetchers.video import fetch_video_content
from app.services.runtime_store import ARTICLES_DB, TASKS_DB, article_from_db_record, task_created_at, update_task
from app.services.article_summary import generate_article_summary
from app.services.settings_store import numeric_setting
from app.services.video_notes import generate_video_notes

def _normalize_title(title: str | None) -> str:
    if title is None:
        return "未知标题"
    text = str(title).strip()
    return text or "未知标题"


def build_local_summary(text: str | None, fallback: str, limit: int = 120) -> str:
    """Create a short local excerpt without sending content to an LLM."""
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text or "")
    value = re.sub(r"[`#>*_~-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return fallback
    limit = max(1, int(limit))
    return value[:limit].rstrip() + ("..." if len(value) > limit else "")


def build_video_markdown(video_payload: dict, summary: str, notes: str = "") -> str:
    transcript = (video_payload.get("transcript_text") or "").strip()
    description = (video_payload.get("description") or "").strip()
    chapters = (video_payload.get("chapter_info") or "").strip()
    if notes.strip():
        # 笔记即最终成品，不附完整文稿
        return notes.strip()
    sections = [
        "## 内容摘要",
        summary,
        "",
        "---",
        "",
        f"# {video_payload.get('title') or '视频内容'}",
        "",
        f"- 作者：{video_payload.get('uploader') or '未知作者'}",
    ]
    if description:
        sections.extend(["", "## 视频简介", "", description])
    if chapters:
        sections.extend(["", "## 章节", "", chapters])
    if transcript:
        sections.extend(["", "## 文稿", "", transcript])
    return "\n".join(sections).strip()


def detect_source_type(url: str) -> str:
    return (
        "bilibili" if "bilibili" in url or "b23.tv" in url else
        "douyin" if "douyin" in url else
        "wechat" if "weixin" in url else
        "x" if ("x.com" in url or "twitter.com" in url) else
        "csdn" if "csdn.net" in url else
        "cnblogs" if "cnblogs.com" in url else
        "other"
    )


async def resolve_article_summary(
    url: str, article_payload: dict, config, summary_limit: int, update_step,
) -> str:
    """微信文章摘要用大模型浓缩全文，其他来源维持本地截取。

    LLM 未配置/调用失败/正文过短时回退本地截取，绝不阻断导入。
    """
    body = article_payload["extracted_md"]
    if "mp.weixin.qq.com" in url:
        try:
            update_step("正在通过大模型浓缩全文生成摘要...")
            return await generate_article_summary(
                article_payload["title"], body, config, limit=summary_limit,
            )
        except Exception as exc:
            update_step(f"大模型摘要不可用：{exc}，回退为本地截取。")
    return build_local_summary(body, "原文正文已获取。", summary_limit)


async def set_processing_status(task_id: str, current_step: str):
    update_task(task_id, status="processing", current_step=current_step)
    async with AsyncSessionLocal() as session:
        db_task = await session.get(Task, task_id)
        if db_task:
            db_task.status = "processing"
            db_task.current_step = current_step
            await session.commit()


async def create_task_record(task_id: str, url: str, created_at_iso: str):
    async with AsyncSessionLocal() as session:
        session.add(
            Task(
                id=task_id,
                original_url=url,
                status="pending",
                current_step="任务已接收",
                created_at=datetime.datetime.fromisoformat(created_at_iso),
            )
        )
        await session.commit()


async def process_task(task_id: str, url: str, config):
    try:
        await set_processing_status(task_id, "正在初始化处理流程...")

        def update_step(step: str):
            update_task(task_id, current_step=step)

        summary_limit = numeric_setting(config or {}, "summaryLength", 120, lo=20, hi=2000, integer=True)
        title = "未知标题"
        summary = ""
        generated_content = ""
        cover_image_url = ""
        source_url = url
        account_name = ""
        publish_time = ""

        if "x.com" in url or "twitter.com" in url:
            direct_article_id = extract_x_article_id(url)
            if direct_article_id:
                raise RuntimeError(
                    "暂不支持 x.com/i/article 直链（TikHub 仅支持推文链接）。请在 X 中打开宿主推文后分享其链接。"
                )

            update_step("正在通过 TikHub 接口获取推文数据...")
            try:
                tikhub_result = await asyncio.to_thread(fetch_tikhub_tweet, url, config)
            except TikHubNotConfiguredError as exc:
                raise RuntimeError(
                    "未配置 TikHub API Token，无法抓取 X 内容。请在管理后台 TikHub 抓取页填写 Token。"
                ) from exc
            tweet_payload = tikhub_result["payload"]

            title = tweet_payload["title"]
            has_tikhub_article = bool(
                tikhub_result.get("article_result") or tikhub_result.get("article_text")
            )
            x_article_id = extract_x_article_id(tweet_payload["tweet_text"])
            external_source_url = next(iter(tweet_payload.get("external_urls") or []), "")
            external_fetched = False

            if external_source_url and not direct_article_id:
                try:
                    update_step("检测到推文引用了外部文章，正在抓取原网页...")
                    article_payload = await fetch_article_content(external_source_url, update_step, config)
                    title = article_payload["title"] or title
                    summary = build_local_summary(article_payload["extracted_md"], "原文正文已获取。", summary_limit)
                    if article_payload["html_content"]:
                        generated_content = (
                            f"## 内容摘要\n\n{summary}\n\n---\n\n"
                            f"<!-- HTML_CONTENT_START -->\n{article_payload['html_content']}\n<!-- HTML_CONTENT_END -->"
                        )
                    else:
                        generated_content = f"## 内容摘要\n\n{summary}\n\n---\n\n{article_payload['extracted_md']}"
                    cover_image_url = article_payload["cover_image_url"] or tweet_payload["cover_image_url"]
                    source_url = external_source_url
                    external_fetched = True
                except Exception:
                    update_step("外部原文抓取失败，正在回退为保存 X 内容...")

            if not external_fetched and (x_article_id or has_tikhub_article):
                x_article_payload = None
                if tikhub_result.get("article_result"):
                    update_step("正在通过 TikHub 数据渲染 X 长文...")
                    rendered = render_twitter_article_result(tikhub_result["article_result"])
                    if rendered.get("content_md"):
                        x_article_payload = {
                            "title": rendered["title"],
                            "content_md": rendered["content_md"],
                            "cover_image_url": rendered.get("cover_image_url") or "",
                        }
                elif tikhub_result.get("article_text"):
                    article_text = tikhub_result["article_text"]
                    if article_text.get("full_text"):
                        update_step("正在读取 TikHub 返回的 X 长文全文...")
                        x_article_payload = {
                            "title": article_text["title"],
                            "content_md": article_text["full_text"],
                            "cover_image_url": article_text.get("cover_image_url") or "",
                        }
                metadata = {
                    **tweet_payload,
                    "title": (x_article_payload or {}).get("title") or title,
                    "full_text": (tikhub_result.get("article_text") or {}).get("full_text", ""),
                }
                try:
                    replica = await fetch_x_article_replica(url, metadata, update_step)
                except Exception as exc:
                    if not x_article_payload:
                        raise TikHubError("X 原文补采失败，且 TikHub 未返回可保存的正文。") from exc
                    replica = {
                        "version": 1, "status": "text-only", "body_html": "", "body_css": "",
                        "title": x_article_payload["title"], "text": x_article_payload["content_md"],
                        "cover_url": x_article_payload.get("cover_image_url") or "",
                        "author_name": tweet_payload.get("author_name", ""),
                        "author_handle": tweet_payload.get("author_handle", ""),
                        "author_avatar_url": tweet_payload.get("author_avatar_url", ""),
                        "created_at": tweet_payload.get("created_at", ""), "source_url": url,
                        "fonts": [], "assets": [], "text_verified": False,
                        "warnings": ["原页面补采失败，当前仅保存 TikHub 正文，配图、动画及原始排版可能缺失。请重新抓取。"],
                    }
                title = replica["title"] or title
                cover_image_url = replica.get("cover_url") or ""
                account_name = replica.get("author_name") or ""
                publish_time = replica.get("created_at") or ""
                summary = build_local_summary(replica["text"], "X 长文正文已获取。", summary_limit)
                generated_content = (
                    f"## 内容摘要\n\n{summary}\n\n---\n\n"
                    f"<!-- X_ARTICLE_START -->\n"
                    f"{json.dumps(replica, ensure_ascii=False)}\n"
                    f"<!-- X_ARTICLE_END -->"
                )

            if not generated_content:
                update_step("解析成功。正在整理原文...")
                raw_text = tweet_payload["tweet_text"]
                if not raw_text and tweet_payload.get("article_preview"):
                    raw_text = tweet_payload["article_preview"].get("preview_text", "")
                summary = build_local_summary(raw_text, "推文正文已获取。", summary_limit)
                generated_content = (
                    f"## 内容摘要\n\n{summary}\n\n---\n\n"
                    f"<!-- X_CONTENT_START -->\n"
                    f"{json.dumps(tweet_payload, ensure_ascii=False)}\n"
                    f"<!-- X_CONTENT_END -->"
                )
            cover_image_url = cover_image_url or tweet_payload["cover_image_url"]

        elif any(domain in url for domain in ["bilibili.com", "douyin.com", "youtube.com", "b23.tv"]):
            update_step("正在通过专用接口解析视频信息...")
            video_payload = await fetch_video_content(url, config, update_step)
            title = video_payload["title"]
            update_step(f"解析成功: {title}。正在整理视频信息...")
            transcript = (video_payload.get("transcript_text") or "").strip()
            notes = ""
            is_bilibili = "bilibili.com" in url or "b23.tv" in url
            if is_bilibili and not transcript:
                # B 站 CC 字幕覆盖率极低，无字幕时下载音频走云端转写；失败不阻断保存
                try:
                    asr_result = await asyncio.to_thread(
                        fetch_bilibili_transcript_via_asr,
                        url, config, update_step,
                        str(video_payload.get("bvid") or ""),
                        str(video_payload.get("cid") or ""),
                    )
                    video_payload["transcript_text"] = asr_result["transcript_text"]
                    video_payload["cid"] = asr_result.get("cid", "")
                    transcript = asr_result["transcript_text"]
                except Exception as exc:
                    update_step(f"音频转写不可用：{exc}")
            if transcript:
                try:
                    notes = await generate_video_notes(video_payload, config, update_step)
                except Exception as exc:
                    update_step(f"学习笔记生成失败：{exc}，回退为文稿保存。")
            summary = build_local_summary(
                notes or transcript or video_payload.get("description"),
                "视频信息已获取。",
                summary_limit,
            )
            generated_content = build_video_markdown(video_payload, summary, notes=notes)
            cover_image_url = video_payload["cover_image_url"]
            account_name = video_payload.get("uploader") or ""
            publish_time = video_payload.get("publish_time") or ""

        else:
            article_payload = await fetch_article_content(url, update_step, config)
            title = article_payload["title"]
            summary = await resolve_article_summary(url, article_payload, config, summary_limit, update_step)
            if article_payload["html_content"]:
                generated_content = (
                    f"## 内容摘要\n\n{summary}\n\n---\n\n"
                    f"<!-- HTML_CONTENT_START -->\n{article_payload['html_content']}\n<!-- HTML_CONTENT_END -->"
                )
            else:
                generated_content = f"## 内容摘要\n\n{summary}\n\n---\n\n{article_payload['extracted_md']}"
            cover_image_url = article_payload["cover_image_url"]
            account_name = article_payload.get("account_name") or ""
            publish_time = article_payload.get("publish_time") or ""

        title = _normalize_title(title)

        article_id = str(uuid.uuid4())
        update_task(task_id, status="completed", current_step="处理完成", article_id=article_id)

        source_type = detect_source_type(source_url)
        article_data = {
            "id": article_id,
            "title": title,
            "summary": summary,
            "content_md": generated_content,
            "original_url": source_url,
            "source_type": source_type,
            "cover_image_url": cover_image_url,
            "account_name": account_name,
            "publish_time": publish_time,
            "created_at": TASKS_DB[task_id]["created_at"],
        }

        TASKS_DB[task_id]["article"] = article_data
        ARTICLES_DB[article_id] = article_data

        async with AsyncSessionLocal() as session:
            session.add(
                Article(
                    id=article_id,
                    title=title,
                    summary=summary,
                    content_md=generated_content,
                    original_url=source_url,
                    source_type=source_type,
                    cover_image_url=cover_image_url,
                    account_name=account_name,
                    publish_time=publish_time,
                    created_at=datetime.datetime.fromisoformat(task_created_at(TASKS_DB[task_id])),
                )
            )
            db_task = await session.get(Task, task_id)
            if db_task:
                db_task.status = "completed"
                db_task.current_step = "处理完成"
                db_task.article_id = article_id
            await session.commit()
    except Exception as exc:
        import traceback

        err_msg = traceback.format_exc()
        update_task(task_id, status="failed", current_step=f"处理失败: {repr(exc)}")
        async with AsyncSessionLocal() as session:
            db_task = await session.get(Task, task_id)
            if db_task:
                db_task.status = "failed"
                db_task.current_step = f"处理失败: {repr(exc)}"
                db_task.error_message = err_msg
                await session.commit()


async def get_task_status(task_id: str):
    task = TASKS_DB.get(task_id)
    if task:
        return task

    async with AsyncSessionLocal() as session:
        db_task = await session.get(Task, task_id)
        if not db_task:
            return {"error": "Task not found"}

        task_data = {
            "id": db_task.id,
            "original_url": db_task.original_url,
            "status": db_task.status,
            "current_step": db_task.current_step,
            "article_id": db_task.article_id,
            "created_at": db_task.created_at.isoformat() if db_task.created_at else "",
        }

        if db_task.article_id:
            db_article = await session.get(Article, db_task.article_id)
            if db_article:
                article_data = article_from_db_record(db_article)
                task_data["article"] = article_data
                ARTICLES_DB[db_article.id] = article_data

        TASKS_DB[task_id] = task_data
        return task_data
