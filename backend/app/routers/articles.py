import asyncio
import datetime
import threading
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sa_delete, func, or_, select, update as sa_update
from fastapi.encoders import jsonable_encoder
from app.database import get_db
from app.models import Article
from app.services.fetchers.article import parse_article_html
from app.services.fetchers.tikhub import fetch_tikhub_tweet
from app.services.article_summary import generate_article_summary
from app.services.runtime_store import ARTICLES_DB, TASKS_DB
from app.services.settings_store import numeric_setting
from app.services.task_service import build_local_summary, detect_source_type
from app.services.related_articles import fetch_related
from app.services.note_export import article_field, build_export_zip, build_note_markdown, safe_filename

from app.services import wechat_summary_regen
from app.routers.config import get_runtime_config
from app.routers.admin_auth import require_admin

router = APIRouter()


class HtmlImportPayload(BaseModel):
    original_url: str = Field(min_length=1)
    html: str = Field(min_length=1)
    title: str | None = None

async def _list_article_summaries(db: AsyncSession, limit: int, offset: int, category: str = '', source: str = '', q: str = '', starred: bool = False) -> dict:
    """列表分页返回元信息列:正文 content_md 仅在详情接口返回。

    limit 上限 50;按 created_at 倒序,offset 渐进翻页。
    category/source/q/starred 为可选过滤,搜索匹配标题、摘要与原文链接。
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
    if starred:
        filters.append(Article.is_starred == True)  # noqa: E712 — SQLAlchemy 布尔过滤惯用写法
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
        Article.is_starred, Article.read_progress,
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
    if not mappings and offset > 0:
        # 窗口 COUNT 随数据行返回,offset 越界的空页拿不到 total——回退独立 COUNT,
        # 保证筛选切换竞态下前端收到的仍是过滤后全集数而不是 0
        count_query = select(func.count()).select_from(Article)
        for condition in filters:
            count_query = count_query.where(condition)
        total = (await db.execute(count_query)).scalar() or 0
    return {"total": total, "data": rows}


@router.get("/")
async def get_articles_slash(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=5, ge=1, le=50, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    category: str = Query(default="", description="按分类过滤,__none__ 为未分类"),
    source: str = Query(default="", description="按来源过滤:wechat/x/bilibili"),
    q: str = Query(default="", description="搜索标题、摘要与原文链接"),
    starred: bool = Query(default=False, description="只看收藏"),
):
    return await _list_article_summaries(db, limit, offset, category, source, q, starred)

@router.get("")
async def get_articles(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=5, ge=1, le=50, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    category: str = Query(default="", description="按分类过滤,__none__ 为未分类"),
    source: str = Query(default="", description="按来源过滤:wechat/x/bilibili"),
    q: str = Query(default="", description="搜索标题、摘要与原文链接"),
    starred: bool = Query(default=False, description="只看收藏"),
):
    return await _list_article_summaries(db, limit, offset, category, source, q, starred)

@router.get("/stats")
async def get_articles_stats(db: AsyncSession = Depends(get_db)):
    """来源聚合计数(供筛选签精确计数,与渐进加载解耦);starred 为收藏计数。"""
    rows = (await db.execute(
        select(Article.source_type, func.count()).group_by(Article.source_type)
    )).all()
    sources = {"wechat": 0, "x": 0, "bilibili": 0, "other": 0}
    total = 0
    for source_type, count in rows:
        key = source_type if source_type in sources else "other"
        sources[key] += count
        total += count
    starred = (await db.execute(
        select(func.count()).select_from(Article).where(Article.is_starred == True)  # noqa: E712
    )).scalar_one()
    return {"sources": sources, "total": total, "starred": starred}


@router.get("/export-batch")
async def export_batch_notes(
    category: str = Query(..., description="按分类导出,__none__ 为未分类"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """分类批量导出笔记 zip:偏重动作(内存/IO)收进后台。必须声明在 /{article_id} 之前,
    否则单段路径被它吃掉返回 404。stdlib zipfile 全内存打包,个人库规模安全。"""
    value = (category or "").strip()
    uncategorized = value in ("__none__", "__none")
    condition = (
        or_(Article.category.is_(None), Article.category == "")
        if uncategorized
        else func.trim(Article.category) == value
    )
    articles = (await db.execute(
        select(Article).where(condition).order_by(Article.created_at.desc())
    )).scalars().all()
    if not articles:
        raise HTTPException(status_code=404, detail="该分类下没有文章")
    zip_bytes = await asyncio.to_thread(build_export_zip, articles)
    label = "未分类" if uncategorized else value
    today = datetime.datetime.now().strftime("%Y%m%d")
    zip_name = safe_filename(f"notes-{label}-{today}") + ".zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        # 分类名含中文:ascii 兜底名 + RFC 5987 filename* 双段,漏 filename* 会乱码
        headers={"Content-Disposition": (
            f'attachment; filename="notes-{today}.zip"; filename*=UTF-8\'\'{quote(zip_name)}'
        )},
    )


@router.get("/{article_id}/export")
async def export_article_note(article_id: str, db: AsyncSession = Depends(get_db)):
    """单篇笔记导出:读者级只读下载动作,与详情接口同暴露面。"""
    article = await db.get(Article, article_id)
    if article is None and article_id in ARTICLES_DB:
        # 内存兜底与详情接口一致;note_export 统一走鸭子字段访问
        article = ARTICLES_DB[article_id]
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    markdown = build_note_markdown(article)
    filename = safe_filename(article_field(article, "title")) + ".md"
    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        # 标题含中文:ascii 兜底用 article id + RFC 5987 filename* 双段
        headers={"Content-Disposition": (
            f'attachment; filename="{article_id}.md"; filename*=UTF-8\'\'{quote(filename)}'
        )},
    )


@router.get("/{article_id}/related")
async def get_related_articles(article_id: str, db: AsyncSession = Depends(get_db)):
    """相关阅读:同分类候选+字符重合度打分的只读推荐;读者级不鉴权,与详情接口同暴露面。"""
    rows = await fetch_related(db, article_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"data": rows}


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
    # 微信文章摘要走大模型浓缩；其他来源/模型不可用回退本地截取
    config = await get_runtime_config()
    summary_limit = int(numeric_setting(config, "summaryLength", 120, lo=20, hi=2000, integer=True))
    summary = build_local_summary(parsed["extracted_md"], "原文正文已导入。", summary_limit)
    if "mp.weixin.qq.com" in data.original_url:
        try:
            summary = await generate_article_summary(title, parsed["extracted_md"], config, limit=summary_limit)
        except Exception:
            pass  # 保持本地截取兜底，导入不失败
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

class BatchIdsPayload(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)


@router.post("/wechat-summaries/regenerate")
async def regenerate_wechat_summaries(_: None = Depends(require_admin)):
    """存量微信文章摘要批量重生成：逐篇走大模型，后台线程跑批，进度走 progress 接口。"""
    if wechat_summary_regen.progress_snapshot()["running"]:
        return {"status": "already-running", **wechat_summary_regen.progress_snapshot()}
    threading.Thread(
        target=lambda: asyncio.run(wechat_summary_regen.regenerate_wechat_summaries()),
        daemon=True,
        name="wechat-summary-regen",
    ).start()
    return {"status": "started", **wechat_summary_regen.progress_snapshot()}


@router.get("/wechat-summaries/progress")
async def wechat_summaries_progress(_: None = Depends(require_admin)):
    return wechat_summary_regen.progress_snapshot()


class BatchCategoryPayload(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)
    category: str | None = Field(default=None, max_length=64)


@router.post("/batch-delete")
async def batch_delete_articles(payload: BatchIdsPayload, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    """批量删除文章并连带清理处理任务与划线笔记;不存在的 id 静默跳过,返回实际删除数。"""
    from app.models import Note, Task
    ids = list(dict.fromkeys(payload.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    task_result = await db.execute(sa_delete(Task).where(Task.article_id.in_(ids)))
    note_result = await db.execute(sa_delete(Note).where(Note.article_id.in_(ids)))
    article_result = await db.execute(sa_delete(Article).where(Article.id.in_(ids)))
    await db.commit()
    for article_id in ids:
        ARTICLES_DB.pop(article_id, None)
    for task_id, task_data in list(TASKS_DB.items()):
        if task_data.get("article_id") in ids:
            del TASKS_DB[task_id]
    return {
        "status": "success",
        "deleted": article_result.rowcount or 0,
        "tasks_deleted": task_result.rowcount or 0,
        "notes_deleted": note_result.rowcount or 0,
    }


@router.patch("/batch-category")
async def batch_update_category(payload: BatchCategoryPayload, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    """批量设置分类;空串/None 归为未分类,与单篇 PATCH 行为一致。"""
    ids = list(dict.fromkeys(payload.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    value = (payload.category or "").strip()
    # Core update 不触发 ORM onupdate,updated_at 需显式带上(详情接口 ETag 依赖它)
    result = await db.execute(
        sa_update(Article)
        .where(Article.id.in_(ids))
        .values(
            category=(value or None),
            updated_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )
    )
    await db.commit()
    for article_id in ids:
        if article_id in ARTICLES_DB:
            ARTICLES_DB[article_id]["category"] = value or None
    return {"status": "success", "updated": result.rowcount or 0}


class ArticleStarPayload(BaseModel):
    starred: bool


@router.patch("/{article_id}/star")
async def toggle_article_star(article_id: str, payload: ArticleStarPayload, db: AsyncSession = Depends(get_db)):
    """收藏/取消收藏。读者级写接口(只翻转标记,不改内容不删数据),同 import-html 惯例不加鉴权。"""
    result = await db.execute(sa_update(Article).where(Article.id == article_id).values(is_starred=payload.starred))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="文章不存在")
    await db.commit()
    # 阅读态是展示元数据而非内容,updated_at 不动;详情 ETag 已单独纳入 is_starred
    if article_id in ARTICLES_DB:
        ARTICLES_DB[article_id]["is_starred"] = payload.starred
    return {"starred": payload.starred}


class ArticleProgressPayload(BaseModel):
    progress: float


@router.put("/{article_id}/progress")
async def update_article_progress(article_id: str, payload: ArticleProgressPayload, db: AsyncSession = Depends(get_db)):
    """上报阅读进度:clamp 到 0~1 后与现值取 max 单调存储(回滚不回退进度)。"""
    row = (await db.execute(
        select(Article.read_progress).where(Article.id == article_id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    current = float(row.read_progress or 0.0)
    next_progress = max(current, min(1.0, max(0.0, payload.progress)))
    if next_progress != current:
        await db.execute(
            sa_update(Article).where(Article.id == article_id).values(read_progress=next_progress)
        )
        await db.commit()
    if article_id in ARTICLES_DB:
        ARTICLES_DB[article_id]["read_progress"] = next_progress
    return {"progress": next_progress}


@router.get("/{article_id}")
async def get_article(
    article_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalars().first()

    if article:
        # 正文不可变(仅分类等元数据可改且会更新 updated_at),ETag 命中时 304 省掉整段正文传输;
        # 收藏/进度只翻标记不动 updated_at,必须一并纳入 ETag,否则翻转后重验证命中 304 会把旧阅读态还回去
        etag = (
            f'W/"{article.id}-{article.updated_at.isoformat() if article.updated_at else "0"}'
            f'-{int(article.is_starred)}-{article.read_progress}"'
        )
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
    from app.models import Note, Task
    result = await db.execute(select(Task).where(Task.article_id == article_id))
    tasks = result.scalars().all()
    for task in tasks:
        await db.delete(task)

    # 划线笔记无外键级联(SQLite 未开 PRAGMA),删文章前显式清理
    await db.execute(sa_delete(Note).where(Note.article_id == article_id))

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
