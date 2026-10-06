import datetime
import uuid

from sqlalchemy import Column, DateTime, Index, String, Text

from app.database import Base


class Article(Base):
    __tablename__ = "articles"
    # 列表页按 created_at 倒序分页,来源/分类是最常用的过滤维度
    __table_args__ = (
        Index("ix_articles_created_at", "created_at"),
        Index("ix_articles_source_created", "source_type", "created_at"),
        Index("ix_articles_category_created", "category", "created_at"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    content_md = Column(Text, nullable=False)
    original_url = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=False)
    cover_image_url = Column(Text, nullable=True)
    account_name = Column(String(255), nullable=True)
    publish_time = Column(String(64), nullable=True)
    category = Column(String(64), nullable=True)
    # 邮件导入来源的 Message-ID:文章被删后重拉凭它放行重新导入
    email_message_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
