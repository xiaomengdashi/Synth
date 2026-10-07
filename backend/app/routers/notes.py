"""划线笔记:读者选中正文文字保存笔记,重进详情页按文本锚定恢复高亮。

读者级接口(创建/按文章列表)不加鉴权——与 PATCH /{id}/star、PUT /{id}/progress
同口径:写的是用户自己的阅读附属数据,只增不改不删文章内容;管理侧(全量列表/删除)
走 require_admin。独立 notes 前缀而非挂 articles 子路径:单段子路径会被
articles 的 /{article_id} 吃掉,且笔记是跨文章实体(后台全量列表)。
"""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Article, Note
from app.routers.admin_auth import require_admin

router = APIRouter()


class NoteCreatePayload(BaseModel):
    article_id: str = Field(min_length=1)
    # 划线原文与前后文指纹:quote/prefix/suffix 由前端从同一正文字符流切片,口径一致
    quote: str = Field(min_length=1, max_length=2000)
    note: str = Field(min_length=1, max_length=2000)
    prefix: str = Field(default="", max_length=128)
    suffix: str = Field(default="", max_length=128)


def _encode_created_at(value: datetime.datetime | None) -> str:
    """created_at 是 UTC naive(同 Task 惯例),JSON 无时区标记会被浏览器按本地时区
    解析(相对时间偏移数小时)——统一补 Z 明示 UTC。"""
    return value.isoformat() + "Z" if value is not None else ""


@router.post("")
async def create_note(payload: NoteCreatePayload, db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, payload.article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    duplicate = (await db.execute(
        select(Note.id).where(Note.article_id == payload.article_id, Note.quote == payload.quote)
    )).first()
    if duplicate:
        # 防重复划同一段:客户端前置拦截,服务端 409 是二道防线(轻微改选区可绕过,个人库可接受)
        raise HTTPException(status_code=409, detail="这段划线已有笔记")
    note = Note(
        article_id=payload.article_id,
        quote=payload.quote,
        note=payload.note,
        prefix=payload.prefix,
        suffix=payload.suffix,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    encoded = jsonable_encoder(note)
    encoded["created_at"] = _encode_created_at(note.created_at)
    return encoded


@router.get("")
async def list_notes(
    article_id: str = Query(..., description="按文章过滤"),
    db: AsyncSession = Depends(get_db),
):
    """读者级:按文章返回笔记,created_at 升序=阅读顺序(正文自上而下恢复高亮)。"""
    rows = (await db.execute(
        select(Note).where(Note.article_id == article_id).order_by(Note.created_at.asc(), Note.id.asc())
    )).scalars().all()
    data = []
    for note in rows:
        encoded = jsonable_encoder(note)
        encoded["created_at"] = _encode_created_at(note.created_at)
        data.append(encoded)
    return {"total": len(rows), "data": data}


@router.get("/all")
async def list_all_notes(
    limit: int = Query(default=50, ge=1, le=200, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    article_id: str = Query(default="", description="按文章筛选"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """后台全量列表:join 文章取标题;total 窗口 COUNT 随行返回,offset 越界空页回退
    独立 COUNT(循 _list_article_summaries 做法);articles 为全表 distinct 有笔记的文章,
    不受当前筛选影响,供表头筛选下拉稳定选项。"""
    filters = [Note.article_id == article_id] if article_id else []
    query = select(
        Note.id, Note.article_id, Article.title.label("article_title"),
        Note.quote, Note.note, Note.created_at,
        func.count().over().label("total"),
    ).join(Article, Article.id == Note.article_id)
    for condition in filters:
        query = query.where(condition)
    mappings = (await db.execute(
        query.order_by(Note.created_at.desc(), Note.id.desc()).limit(limit).offset(offset)
    )).mappings().all()
    rows = []
    for row in mappings:
        item = {k: v for k, v in row.items() if k != "total"}
        item["created_at"] = _encode_created_at(item.get("created_at"))
        rows.append(item)

    total = mappings[0]["total"] if mappings else 0
    if not mappings and offset > 0:
        # 窗口 COUNT 随数据行返回,offset 越界的空页拿不到 total——回退独立 COUNT
        count_query = select(func.count()).select_from(Note).join(Article, Article.id == Note.article_id)
        for condition in filters:
            count_query = count_query.where(condition)
        total = (await db.execute(count_query)).scalar() or 0

    article_options = (await db.execute(
        select(Article.id, Article.title)
        .join(Note, Note.article_id == Article.id)
        .distinct()
        .order_by(Article.created_at.desc())
    )).all()
    return {
        "total": total,
        "data": rows,
        "articles": [{"id": row[0], "title": row[1]} for row in article_options],
    }


@router.delete("/{note_id}")
async def delete_note(note_id: str, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    result = await db.execute(sa_delete(Note).where(Note.id == note_id))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="笔记不存在")
    await db.commit()
    return {"status": "success"}
