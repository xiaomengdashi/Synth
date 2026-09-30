import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.database import Base


class AppSetting(Base):
    """应用配置项（key-value），存储在 SQLite 中，取代旧的 data/config.json。"""

    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
