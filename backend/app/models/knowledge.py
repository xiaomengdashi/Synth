"""Knowledge conversations, evidence snapshots and rebuildable search data."""
import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.database import Base


def utc_now():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class KnowledgeConversation(Base):
    __tablename__ = 'knowledge_conversations'
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(80), nullable=False, default='新会话')
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)


class KnowledgeTurn(Base):
    __tablename__ = 'knowledge_turns'
    __table_args__ = (
        UniqueConstraint('conversation_id', 'request_id'),
        Index('ix_knowledge_turn_conversation', 'conversation_id', 'created_at'),
    )
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, nullable=False)
    request_id = Column(String(128), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False, default='')
    status = Column(String(20), nullable=False, default='pending')
    insufficient_evidence = Column(Boolean, nullable=False, default=False)
    sources_json = Column(Text, nullable=False, default='[]')
    error_message = Column(Text, nullable=False, default='')
    created_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime, nullable=True)


class KnowledgeIndexedArticle(Base):
    __tablename__ = 'knowledge_indexed_articles'
    article_id = Column(String, primary_key=True)
    article_updated_at = Column(String, nullable=False)
    content_hash = Column(String(64), nullable=False)
    index_version = Column(Integer, nullable=False)
    searchable = Column(Boolean, nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'
    __table_args__ = (UniqueConstraint('article_id', 'position'),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(String, nullable=False, index=True)
    position = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
