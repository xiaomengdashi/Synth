import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from app.database import Base


class Note(Base):
    """划线笔记:读者选中正文文字保存的 quote+笔记,重进详情页按文本锚定恢复高亮。

    前后文指纹(prefix/suffix 各 ≤32 字符)与 quote 一起构成纯文本锚点,
    不依赖 DOM 路径——正文重渲染/图片后到改布局都不影响文本匹配。
    不支持编辑,无 updated_at,保持最小化。
    """

    __tablename__ = "notes"
    # 读者按文章取笔记(created_at 升序=阅读顺序)、后台按文章筛选走复合索引;后台全量倒序走单列
    __table_args__ = (
        Index("ix_notes_article_created", "article_id", "created_at"),
        Index("ix_notes_created_at", "created_at"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # SQLite 未开外键 PRAGMA,不依赖级联;删文章由路由显式清理(同 Task 惯例)
    article_id = Column(String, ForeignKey("articles.id"), nullable=False)
    quote = Column(Text, nullable=False)
    prefix = Column(String(128), nullable=False, default="")
    suffix = Column(String(128), nullable=False, default="")
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None))
