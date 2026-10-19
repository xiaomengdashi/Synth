"""Rebuildable SQLite evidence index; no changes to source articles."""
import asyncio
import hashlib

from sqlalchemy import text, select, delete, func
from sqlalchemy.exc import OperationalError


FTS_DDL = 'CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(title_tokens, body_tokens)'
INDEX_VERSION = 1
_index_lock = asyncio.Lock()


async def initialize_knowledge(connection) -> bool:
    await connection.execute(text(
        "UPDATE knowledge_turns SET status='interrupted', "
        "error_message='服务已重启，请重新提问。', completed_at=CURRENT_TIMESTAMP WHERE status='pending'"
    ))
    try:
        await connection.execute(text(FTS_DDL))
    except OperationalError as exc:
        if 'no such module: fts5' in str(exc).lower():
            return False
        raise
    return True


async def get_index_status(db):
    from app.models import Article
    from app.models.knowledge import KnowledgeIndexedArticle
    available = bool(await db.scalar(text("SELECT 1 FROM sqlite_master WHERE name='knowledge_chunks_fts'")))
    count = await db.scalar(select(func.count()).select_from(Article))
    indexed = await db.scalar(select(func.count()).select_from(KnowledgeIndexedArticle).join(Article, Article.id == KnowledgeIndexedArticle.article_id))
    unsearchable = await db.scalar(select(func.count()).select_from(KnowledgeIndexedArticle).join(Article, Article.id == KnowledgeIndexedArticle.article_id).where(KnowledgeIndexedArticle.searchable == False))
    await db.commit()
    return dict(index_available=available, article_count=count, indexed_count=indexed, unsearchable_count=unsearchable)


def _prepare(rows):
    from app.services.knowledge_retrieval import extract_search_text, split_chunks, tokenize
    prepared = []
    for row in rows:
        chunks = split_chunks(extract_search_text(row['content_md']))
        prepared.append((row, hashlib.sha256((row['title'] + '\0' + row['content_md']).encode()).hexdigest(),
                         ' '.join(tokenize(row['title'])), [(chunk, ' '.join(tokenize(chunk))) for chunk in chunks]))
    return prepared


async def _remove_chunks(db, article_id):
    from app.models.knowledge import KnowledgeChunk
    await db.execute(text('DELETE FROM knowledge_chunks_fts WHERE rowid IN (SELECT id FROM knowledge_chunks WHERE article_id=:id)'), {'id': article_id})
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))


async def sync_knowledge_index(db):
    from app.models import Article
    from app.models.knowledge import KnowledgeIndexedArticle, KnowledgeChunk
    async with _index_lock:
        # The source projection covers the whole collection; only changed bodies are loaded.
        versions = {r.id: r.updated_at.isoformat() if r.updated_at else '' for r in (await db.execute(select(Article.id, Article.updated_at)))}
        indexed = {r.article_id: dict(r) for r in (await db.execute(select(KnowledgeIndexedArticle.__table__))).mappings()}
        await db.commit()
        for removed in indexed.keys() - versions.keys():
            await _remove_chunks(db, removed)
            await db.execute(delete(KnowledgeIndexedArticle).where(KnowledgeIndexedArticle.article_id == removed))
        await db.commit()
        changed = [key for key, version in versions.items() if key not in indexed or indexed[key]['article_updated_at'] != version or indexed[key]['index_version'] != INDEX_VERSION]
        for start in range(0, len(changed), 64):
            rows = (await db.execute(select(Article.id, Article.title, Article.content_md, Article.updated_at).where(Article.id.in_(changed[start:start + 64])))).mappings().all()
            await db.commit()
            prepared = await asyncio.to_thread(_prepare, rows)
            for row, digest, title_tokens, pieces in prepared:
                key = row['id']
                existing = indexed.get(key)
                if not existing or digest != existing['content_hash'] or existing['index_version'] != INDEX_VERSION:
                    await _remove_chunks(db, key)
                    records = [KnowledgeChunk(article_id=key, position=i, text=piece) for i, (piece, _) in enumerate(pieces)]
                    db.add_all(records)
                    await db.flush()
                    if records:
                        await db.execute(text('INSERT INTO knowledge_chunks_fts(rowid,title_tokens,body_tokens) VALUES (:id,:title,:body)'), [dict(id=record.id, title=title_tokens, body=pieces[i][1]) for i, record in enumerate(records)])
                record = await db.get(KnowledgeIndexedArticle, key)
                if record is None:
                    record = KnowledgeIndexedArticle(article_id=key)
                    db.add(record)
                record.article_updated_at = row['updated_at'].isoformat() if row['updated_at'] else ''
                record.content_hash = digest
                record.index_version = INDEX_VERSION
                record.searchable = bool(pieces)
            await db.commit()
