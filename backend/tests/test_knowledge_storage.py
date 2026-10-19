import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base


def test_create_all_registers_knowledge_tables(tmp_path):
    from app.models.knowledge import KnowledgeConversation, KnowledgeTurn
    from app.services.knowledge_index import initialize_knowledge

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            assert await initialize_knowledge(conn)
        async with sessions() as db:
            db.add(KnowledgeConversation(id='a'))
            db.add(KnowledgeConversation(id='b'))
            db.add_all([
                KnowledgeTurn(conversation_id='a', request_id='r', question='问题'),
                KnowledgeTurn(conversation_id='b', request_id='r', question='别的问题', status='completed'),
            ])
            await db.commit()
        async with engine.begin() as conn:
            await initialize_knowledge(conn)
            await initialize_knowledge(conn)
        async with sessions() as db:
            turns = (await db.scalars(select(KnowledgeTurn).order_by(KnowledgeTurn.conversation_id))).all()
            assert [t.status for t in turns] == ['interrupted', 'completed']
            db.add(KnowledgeTurn(conversation_id='a', request_id='r', question='重复'))
            with pytest.raises(IntegrityError):
                await db.commit()
        await engine.dispose()
    asyncio.run(run())


def test_missing_fts_keeps_core_database_usable():
    from app.services.knowledge_index import initialize_knowledge

    class MissingFTS:
        async def execute(self, statement):
            if 'VIRTUAL' in str(statement):
                raise OperationalError(str(statement), {}, Exception('no such module: fts5'))
            return None
    assert asyncio.run(initialize_knowledge(MissingFTS())) is False
