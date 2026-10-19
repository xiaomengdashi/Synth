"""Rebuildable SQLite evidence index; no changes to source articles."""
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


FTS_DDL = 'CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(title_tokens, body_tokens)'


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
