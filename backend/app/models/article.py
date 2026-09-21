import datetime
import uuid

from sqlalchemy import Column, DateTime, String, Text

from app.database import Base


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
