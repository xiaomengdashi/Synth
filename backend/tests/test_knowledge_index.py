import asyncio
import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Article
from app.models.knowledge import KnowledgeChunk, KnowledgeIndexedArticle
from app.services.knowledge_index import initialize_knowledge, sync_knowledge_index, get_index_status
from app.services.knowledge_retrieval import retrieve_chunks


def with_database(tmp_path, scenario):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'index.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await initialize_knowledge(conn)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()
    asyncio.run(run())


def article(key, body, title='普通标题'):
    return Article(id=key, title=title, summary='普通摘要', content_md=body, original_url='', source_type='other')


def test_body_only_match_in_old_article_tail(tmp_path):
    async def scenario(db):
        old = article('old', ''.join(f'第{i}段不重复的普通段落。' for i in range(2000)) + '\n量化缓存采用低位宽保存键值。')
        old.created_at = datetime.datetime(2020, 1, 1)
        db.add(old)
        db.add_all([article(str(i), '烹饪与散步。') for i in range(70)])
        await db.commit()
        await sync_knowledge_index(db)
        rows = await retrieve_chunks(db, '量化缓存', previous_questions=[], previous_article_ids=[])
        assert rows and rows[0].article_id == 'old'
        assert '低位宽' in rows[0].text
        assert not db.in_transaction()
    with_database(tmp_path, scenario)


def test_sync_add_edit_delete_and_version_rebuild(tmp_path):
    async def scenario(db):
        db.add(article('one', 'SQLite 事务隔离。'))
        await db.commit()
        await sync_knowledge_index(db)
        first = (await db.scalars(select(KnowledgeChunk.id))).all()
        await sync_knowledge_index(db)
        assert (await db.scalars(select(KnowledgeChunk.id))).all() == first
        await db.execute(update(Article).where(Article.id == 'one').values(content_md='Redis 内存缓存。', title='新标题'))
        await db.commit()
        await sync_knowledge_index(db)
        assert not await retrieve_chunks(db, 'SQLite', previous_questions=[], previous_article_ids=[])
        assert (await retrieve_chunks(db, 'Redis', previous_questions=[], previous_article_ids=[]))[0].title == '新标题'
        await db.execute(update(KnowledgeIndexedArticle).values(index_version=0))
        await db.commit()
        await sync_knowledge_index(db)
        assert (await db.get(KnowledgeIndexedArticle, 'one')).index_version > 0
        await db.execute(delete(Article))
        await db.commit()
        await sync_knowledge_index(db)
        assert not await retrieve_chunks(db, 'Redis', previous_questions=[], previous_article_ids=[])
    with_database(tmp_path, scenario)


def test_empty_or_corrupt_bodies_count_unsearchable(tmp_path):
    async def scenario(db):
        db.add(article('bad', '<!-- X_ARTICLE_START -->broken<!-- X_ARTICLE_END -->'))
        await db.commit()
        await sync_knowledge_index(db)
        status = await get_index_status(db)
        assert status['unsearchable_count'] == 1 and status['article_count'] == 1
    with_database(tmp_path, scenario)


def test_follow_up_reuses_topic_without_overriding_new_question(tmp_path):
    async def scenario(db):
        db.add_all([article('sql', 'SQLite 支持持久化事务。'), article('redis', 'Redis 提供内存缓存。')])
        await db.commit()
        await sync_knowledge_index(db)
        follow = await retrieve_chunks(db, '再展开讲讲', previous_questions=['SQLite 事务'], previous_article_ids=['sql'])
        assert follow and follow[0].article_id == 'sql'
        repeated = await retrieve_chunks(db, '再展开讲讲', previous_questions=['再展开', '讲讲'], previous_article_ids=['sql'])
        assert repeated and all(row.article_id == 'sql' for row in repeated)
        changed = await retrieve_chunks(db, 'Redis', previous_questions=['SQLite 事务'], previous_article_ids=['sql'])
        assert changed and all(row.article_id == 'redis' for row in changed)
    with_database(tmp_path, scenario)


def test_retrieval_limits_and_diversifies_sources(tmp_path):
    async def scenario(db):
        for i in range(8):
            db.add(article(str(i), ''.join(f'Redis 方案{i}第{j}段缓存策略。' * 30 for j in range(20))))
        await db.commit()
        await sync_knowledge_index(db)
        rows = await retrieve_chunks(db, 'Redis', previous_questions=[], previous_article_ids=[])
        assert 1 < len({r.article_id for r in rows})
        assert len(rows) <= 12 and sum(len(r.text) for r in rows) <= 14400
        assert all(sum(r.article_id == key for r in rows) <= 3 for key in {r.article_id for r in rows})
    with_database(tmp_path, scenario)
