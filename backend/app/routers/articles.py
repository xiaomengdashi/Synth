from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from app.database import get_db
from app.models import Article
from app.routers.tasks import ARTICLES_DB

router = APIRouter()

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
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    await db.delete(article)
    await db.commit()
    
    # 顺便清理内存中的数据
    from app.routers.tasks import ARTICLES_DB, TASKS_DB
    if article_id in ARTICLES_DB:
        del ARTICLES_DB[article_id]
    
    # 清理 TASKS_DB 中对应的任务
    task_ids_to_del = [tid for tid, tdata in TASKS_DB.items() if tdata.get("article_id") == article_id]
    for tid in task_ids_to_del:
        del TASKS_DB[tid]
        
    return {"status": "success", "message": "Article deleted"}
