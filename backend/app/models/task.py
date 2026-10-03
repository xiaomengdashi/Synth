import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_created_at", "created_at"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    original_url = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    current_step = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    article_id = Column(String, ForeignKey("articles.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None))
