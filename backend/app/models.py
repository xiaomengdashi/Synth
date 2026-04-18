from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import datetime
from .database import Base

class Article(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    content_md = Column(Text, nullable=False)
    original_url = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=False)
    cover_image_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    original_url = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    current_step = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    article_id = Column(String, ForeignKey("articles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
