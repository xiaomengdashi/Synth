"""
数据库初始化与会话管理
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """创建所有数据库表"""
    from . import models  # noqa: F401 — 触发模型注册
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会给已有表加列，轻量迁移补充新列
        from sqlalchemy import text

        for column in ("account_name", "publish_time", "category"):
            try:
                await conn.execute(
                    text(f"ALTER TABLE articles ADD COLUMN {column} VARCHAR(255)")
                )
            except Exception:
                pass  # 列已存在

        # create_all 只对新建的表生效,已有库的索引在这里幂等补建
        for ddl in (
            "CREATE INDEX IF NOT EXISTS ix_articles_created_at ON articles (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_articles_source_created ON articles (source_type, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_articles_category_created ON articles (category, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_created_at ON tasks (created_at)",
        ):
            await conn.execute(text(ddl))


async def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
