import asyncio
import datetime
import json
import re
import uuid
import urllib.parse

from app.database import AsyncSessionLocal
from app.models import Article, Task
from app.services.fetchers.article import fetch_article_content
from app.services.fetchers.social import fetch_tweet_data, normalize_tweet_payload
from app.services.fetchers.video import fetch_video_content
from app.services.fetchers.x_twitter_cli import extract_x_article_id, fetch_x_article_via_twitter_cli
from app.services.runtime_store import ARTICLES_DB, TASKS_DB, article_from_db_record, task_created_at, update_task

def _normalize_title(title: str | None) -> str:
    if title is None:
        return "未知标题"
    text = str(title).strip()
    return text or "未知标题"


def build_local_summary(text: str | None, fallback: str) -> str:
    """Create a short local excerpt without sending content to an LLM."""
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text or "")
    value = re.sub(r"[`#>*_~-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return fallback
    return value[:120].rstrip() + ("..." if len(value) > 120 else "")


def build_video_markdown(video_payload: dict, summary: str) -> str:
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
    description = (video_payload.get("description") or "").strip()
    chapters = (video_payload.get("chapter_info") or "").strip()
    transcript = (video_payload.get("transcript_text") or "").strip()
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

        title = "未知标题"
        summary = ""
        generated_content = ""
        cover_image_url = ""
        source_url = url

        if "x.com" in url or "twitter.com" in url:
            update_step("正在尝试获取推文信息...")
            direct_article_id = extract_x_article_id(url)
            tweet_payload = normalize_tweet_payload({}) if direct_article_id else normalize_tweet_payload(await asyncio.to_thread(fetch_tweet_data, url))
            title = tweet_payload["title"]
            x_article_id = direct_article_id or extract_x_article_id(tweet_payload["tweet_text"])
            external_source_url = next(iter(tweet_payload.get("external_urls") or []), "")
            external_fetched = False

            if external_source_url and not direct_article_id:
                try:
                    update_step("检测到推文引用了外部文章，正在抓取原网页...")
                    article_payload = await fetch_article_content(external_source_url, update_step)
                    title = article_payload["title"] or title
                    summary = build_local_summary(article_payload["extracted_md"], "原文正文已获取。")
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

            if not external_fetched and x_article_id:
                x_cli_payload = await fetch_x_article_via_twitter_cli(url, update_step)
                title = x_cli_payload["title"] or title
                cover_image_url = x_cli_payload.get("cover_image_url") or ""
                summary = build_local_summary(x_cli_payload["content_md"], "X 长文正文已获取。")
                generated_content = (
                    f"## 内容摘要\n\n{summary}\n\n---\n\n"
                    f"<!-- X_CONTENT_START -->\n"
                    f"{x_cli_payload['content_md']}\n"
                    f"<!-- X_CONTENT_END -->"
                )

            if not generated_content:
                update_step("解析成功。正在整理原文...")
                raw_text = tweet_payload["tweet_text"]
                if not raw_text and tweet_payload.get("article_preview"):
                    raw_text = tweet_payload["article_preview"].get("preview_text", "")
                summary = build_local_summary(raw_text, "推文正文已获取。")
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
            summary = build_local_summary(
                video_payload.get("transcript_text") or video_payload.get("description"),
                "视频信息已获取。",
            )
            generated_content = build_video_markdown(video_payload, summary)
            cover_image_url = video_payload["cover_image_url"]

        else:
            article_payload = await fetch_article_content(url, update_step)
            title = article_payload["title"]
            summary = build_local_summary(article_payload["extracted_md"], "原文正文已获取。")
            if article_payload["html_content"]:
                generated_content = (
                    f"## 内容摘要\n\n{summary}\n\n---\n\n"
                    f"<!-- HTML_CONTENT_START -->\n{article_payload['html_content']}\n<!-- HTML_CONTENT_END -->"
                )
            else:
                generated_content = f"## 内容摘要\n\n{summary}\n\n---\n\n{article_payload['extracted_md']}"
            cover_image_url = article_payload["cover_image_url"]

        title = _normalize_title(title)

        article_id = str(uuid.uuid4())
        update_task(task_id, status="completed", current_step="处理完成", article_id=article_id)

        if not cover_image_url:
            img_prompt = urllib.parse.quote(f"Technology AI abstract {title[:10]}")
            cover_image_url = f"https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt={img_prompt}&image_size=landscape_16_9"

        article_data = {
            "id": article_id,
            "title": title,
            "summary": summary,
            "content_md": generated_content,
            "original_url": source_url,
            "source_type": detect_source_type(source_url),
            "cover_image_url": cover_image_url,
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
                    source_type=detect_source_type(source_url),
                    cover_image_url=cover_image_url,
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
