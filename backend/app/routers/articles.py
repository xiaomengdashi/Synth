import asyncio
import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select
from fastapi.encoders import jsonable_encoder
from app.database import get_db
from app.models import Article
from app.services.fetchers.article import parse_article_html
from app.services.fetchers.tikhub import fetch_tikhub_tweet
from app.services.runtime_store import ARTICLES_DB, TASKS_DB
from app.services.task_service import build_local_summary, detect_source_type
from app.routers.config import get_runtime_config
from app.routers.admin_auth import require_admin

router = APIRouter()


class HtmlImportPayload(BaseModel):
    original_url: str = Field(min_length=1)
    html: str = Field(min_length=1)
    title: str | None = None

async def _list_article_summaries(db: AsyncSession, limit: int, offset: int, category: str = '', source: str = '', q: str = '') -> dict:
    """列表分页返回元信息列:正文 content_md 仅在详情接口返回。

    limit 上限 50;按 created_at 倒序,offset 渐进翻页。
    category/source/q 为可选过滤,搜索匹配标题、摘要与原文链接。
    """
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    filters = []
    if category in ('__none__', '__none'):
        filters.append((Article.category.is_(None)) | (Article.category == ''))
    elif category:
        filters.append(func.trim(Article.category) == category)
    if source:
        filters.append(Article.source_type == source)
    if q:
        keyword = f"%{q.strip()}%"
        filters.append(or_(
            Article.title.ilike(keyword),
            Article.summary.ilike(keyword),
            Article.original_url.ilike(keyword),
        ))
    query = select(
        Article.id, Article.title, Article.summary, Article.source_type,
        Article.cover_image_url, Article.account_name, Article.publish_time,
        Article.category, Article.created_at, Article.updated_at,
        # 窗口函数随本页数据一并给出过滤后的总数,省掉原来单独的 COUNT 查询往返
        func.count().over().label("total"),
    )
    for condition in filters:
        query = query.where(condition)
    result = await db.execute(
        query.order_by(Article.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    mappings = result.mappings().all()
    rows = [{k: v for k, v in row.items() if k != "total"} for row in mappings]

    # 内存兜底仅在无任何过滤时生效;带过滤条件时必须走 DB 计数,否则搜索会静默漏结果
    if not rows and offset == 0 and not filters and ARTICLES_DB:
        return {"total": len(ARTICLES_DB), "data": list(ARTICLES_DB.values())}

    total = mappings[0]["total"] if mappings else 0
    return {"total": total, "data": rows}


@router.get("/")
async def get_articles_slash(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=5, ge=1, le=50, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    category: str = Query(default="", description="按分类过滤,__none__ 为未分类"),
    source: str = Query(default="", description="按来源过滤:wechat/x/bilibili"),
    q: str = Query(default="", description="搜索标题、摘要与原文链接"),
):
    return await _list_article_summaries(db, limit, offset, category, source, q)

@router.get("")
async def get_articles(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=5, ge=1, le=50, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    category: str = Query(default="", description="按分类过滤,__none__ 为未分类"),
    source: str = Query(default="", description="按来源过滤:wechat/x/bilibili"),
    q: str = Query(default="", description="搜索标题、摘要与原文链接"),
):
    return await _list_article_summaries(db, limit, offset, category, source, q)

@router.get("/stats")
async def get_articles_stats(db: AsyncSession = Depends(get_db)):
    """来源聚合计数(供筛选签精确计数,与渐进加载解耦)。"""
    rows = (await db.execute(
        select(Article.source_type, func.count()).group_by(Article.source_type)
    )).all()
    sources = {"wechat": 0, "x": 0, "bilibili": 0, "other": 0}
    total = 0
    for source_type, count in rows:
        key = source_type if source_type in sources else "other"
        sources[key] += count
        total += count
    return {"sources": sources, "total": total}

@router.get("/x-preview")
async def get_x_preview(url: str = Query(..., description="原始 X/Twitter 链接")):
    try:
        return (await asyncio.to_thread(fetch_tikhub_tweet, url, await get_runtime_config()))["payload"]
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
        "account_name": parsed.get("account_name") or "",
        "publish_time": parsed.get("publish_time") or "",
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
            account_name=parsed.get("account_name") or "",
            publish_time=parsed.get("publish_time") or "",
            created_at=created_at,
        )
    )
    await db.commit()
    ARTICLES_DB[article_id] = article_data
    return article_data

@router.get("/{article_id}")
async def get_article(
    article_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalars().first()

    if article:
        # 正文不可变(仅分类等元数据可改且会更新 updated_at),ETag 命中时 304 省掉整段正文传输
        etag = f'W/"{article.id}-{article.updated_at.isoformat() if article.updated_at else "0"}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={
                "ETag": etag,
                "Cache-Control": "private, no-cache",
            })
        return JSONResponse(
            content=jsonable_encoder(article),
            headers={"ETag": etag, "Cache-Control": "private, no-cache"},
        )

    # 如果数据库找不到，尝试从内存数据里找
    if article_id in ARTICLES_DB:
        return ARTICLES_DB[article_id]

    raise HTTPException(status_code=404, detail="Article not found")

class ArticleCategoryPayload(BaseModel):
    category: str | None = Field(default=None, max_length=64)


@router.patch("/{article_id}")
async def update_article_category(article_id: str, payload: ArticleCategoryPayload, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")

    value = (payload.category or "").strip()
    article.category = value if value else None
    await db.commit()
    await db.refresh(article)
    return jsonable_encoder(article)


@router.delete("/{article_id}")
async def delete_article(article_id: str, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
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
