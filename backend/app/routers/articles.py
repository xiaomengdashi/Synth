import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from app.database import get_db
from app.models import Article
from app.services.fetchers.article import parse_article_html
from app.services.fetchers.social import fetch_tweet_data, normalize_tweet_payload
from app.services.runtime_store import ARTICLES_DB, TASKS_DB
from app.services.task_service import build_local_summary, detect_source_type

router = APIRouter()


class HtmlImportPayload(BaseModel):
    original_url: str = Field(min_length=1)
    html: str = Field(min_length=1)
    title: str | None = None

@router.get("/")
async def get_articles_slash(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).order_by(Article.created_at.desc()).limit(50))
    articles = result.scalars().all()
    
    if not articles and ARTICLES_DB:
        return {"total": len(ARTICLES_DB), "data": list(ARTICLES_DB.values())}
        
    return {"total": len(articles), "data": jsonable_encoder(articles)}

@router.get("")
async def get_articles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).order_by(Article.created_at.desc()).limit(50))
    articles = result.scalars().all()
    
    if not articles and ARTICLES_DB:
        return {"total": len(ARTICLES_DB), "data": list(ARTICLES_DB.values())}
        
    return {"total": len(articles), "data": jsonable_encoder(articles)}

@router.get("/x-preview")
async def get_x_preview(url: str = Query(..., description="原始 X/Twitter 链接")):
    try:
        return normalize_tweet_payload(fetch_tweet_data(url))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/import-html")
async def import_html(data: HtmlImportPayload, db: AsyncSession = Depends(get_db)):
    """Import a saved page without opening a browser or fetching the URL."""
    try:
        parsed = parse_article_html(data.original_url.strip(), data.html)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = (data.title or parsed["title"] or "未知标题").strip()
    summary = build_local_summary(parsed["extracted_md"], "原文正文已导入。")
    content_md = (
        f"## 内容摘要\n\n{summary}\n\n---\n\n"
        f"<!-- HTML_CONTENT_START -->\n{parsed['html_content']}\n<!-- HTML_CONTENT_END -->"
    )
    article_id = str(uuid.uuid4())
    created_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    article_data = {
        "id": article_id,
        "title": title,
        "summary": summary,
        "content_md": content_md,
        "original_url": data.original_url.strip(),
        "source_type": detect_source_type(data.original_url),
        "cover_image_url": parsed["cover_image_url"],
        "created_at": created_at.isoformat(),
    }

    db.add(
        Article(
            id=article_id,
            title=title,
            summary=summary,
            content_md=content_md,
            original_url=data.original_url.strip(),
            source_type=detect_source_type(data.original_url),
            cover_image_url=parsed["cover_image_url"],
            created_at=created_at,
        )
    )
    await db.commit()
    ARTICLES_DB[article_id] = article_data
    return article_data

@router.get("/{article_id}")
async def get_article(article_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalars().first()
    
    if article:
        return jsonable_encoder(article)
        
    # 如果数据库找不到，尝试从内存数据里找
    if article_id in ARTICLES_DB:
        return ARTICLES_DB[article_id]
        
    raise HTTPException(status_code=404, detail="Article not found")

@router.delete("/{article_id}")
async def delete_article(article_id: str, db: AsyncSession = Depends(get_db)):
    # 先找到关联的任务并删除（或者置空）
    from app.models import Task
    result = await db.execute(select(Task).where(Task.article_id == article_id))
    tasks = result.scalars().all()
    for task in tasks:
        await db.delete(task)
        
    article = await db.get(Article, article_id)
    if article:
        await db.delete(article)

    if not article and article_id not in ARTICLES_DB:
        raise HTTPException(status_code=404, detail="Article not found")

    await db.commit()

    # 顺便清理内存中的数据
    if article_id in ARTICLES_DB:
        del ARTICLES_DB[article_id]
    
    # 清理 TASKS_DB 中对应的任务
    task_ids_to_del = [tid for tid, tdata in TASKS_DB.items() if tdata.get("article_id") == article_id]
    for tid in task_ids_to_del:
        del TASKS_DB[tid]
        
    return {"status": "success", "message": "Article deleted"}
