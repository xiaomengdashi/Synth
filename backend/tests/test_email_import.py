import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.routers.email_import as email_import
from app.database import Base
from app.models import Article
from app.services import settings_store
from app.services.email_client import EmailMessageData
from app.services.runtime_store import ARTICLES_DB


def _setup(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(email_import, "AsyncSessionLocal", sessions)
    ARTICLES_DB.clear()
    return engine, sessions


def _client():
    app = FastAPI()
    app.include_router(email_import.router, prefix="/api/v1/email")
    return TestClient(app)


def _message(message_id: str, md: str | None) -> EmailMessageData:
    attachments = [{"filename": "notes.md", "content": md}] if md is not None else []
    return EmailMessageData(
        message_id=message_id, from_addr="zhang@163.com",
        subject="B站笔记", date="2026-10-04 10:30", md_attachments=attachments,
    )


def test_fetch_imports_md_and_dedupes(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config: [_message("msg-1", "# 网络原理\n\nhttps://b23.tv/abc"), _message("msg-2", None)],
    )
    client = _client()

    first = client.post("/api/v1/email/fetch").json()
    assert first["fetched"] == 2
    assert len(first["imported"]) == 1
    assert first["imported"][0]["title"] == "网络原理"
    assert first["skipped"] == [{"subject": "B站笔记", "reason": "邮件没有 .md 附件"}]

    second = client.post("/api/v1/email/fetch").json()
    assert second["imported"] == []
    # msg-2 无附件每次都会出现在跳过列表;真实链路里它已在 fetch 层被过滤,走不到这里
    assert second["skipped"] == [
        {"subject": "B站笔记", "reason": "已导入过，跳过"},
        {"subject": "B站笔记", "reason": "邮件没有 .md 附件"},
    ]
    asyncio.run(engine.dispose())


def test_imported_article_fields(tmp_path, monkeypatch):
    engine, sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages", lambda config: [_message("msg-1", "# 标题\n\n正文")]
    )
    client = _client()
    data = client.post("/api/v1/email/fetch").json()
    article_id = data["imported"][0]["id"]

    async def load():
        async with sessions() as session:
            return await session.get(Article, article_id)

    article = asyncio.run(load())
    assert article is not None
    assert article.source_type == "bilibili"
    assert article.original_url == ""  # 测试正文里没有 B 站链接
    assert article.content_md == "# 标题\n\n正文"
    assert article.account_name == "zhang@163.com"
    assert article.publish_time == "2026-10-04 10:30"
    assert article.id in ARTICLES_DB
    asyncio.run(engine.dispose())


def test_fetch_without_whitelist_returns_chinese_400(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    from app.services.email_client import EmailFetchError

    def raise_no_whitelist(config):
        raise EmailFetchError("请先配置发件人白名单，再拉取邮件。")

    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", raise_no_whitelist)
    response = _client().post("/api/v1/email/fetch")
    assert response.status_code == 400
    assert "白名单" in response.json()["detail"]
    asyncio.run(engine.dispose())


def test_test_endpoint_reports_recent_count(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", lambda config: [_message("m1", "# t")])
    data = _client().post("/api/v1/email/test").json()
    assert data == {"ok": True, "recent_count": 1}
    asyncio.run(engine.dispose())


def test_fetch_covers_real_bilibili_video(tmp_path, monkeypatch):
    """正文带B站链接:取官方真实封面并本地化。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config: [_message("cover-1", "# 封面\n\nhttps://www.bilibili.com/video/BV17x6hYZEzJ")],
    )
    monkeypatch.setattr(email_import, "_fetch_bilibili_official_view", lambda bvid: {"pic": "https://i0.hdslb.com/bfs/x.jpg"})
    monkeypatch.setattr(email_import, "_localize_bilibili_cover", lambda pic, bvid: f"/media/bilibili/{bvid}.jpg")
    client = _client()
    data = client.post("/api/v1/email/fetch").json()
    assert data["imported"][0]["id"] in ARTICLES_DB
    assert ARTICLES_DB[data["imported"][0]["id"]]["cover_image_url"] == "/media/bilibili/BV17x6hYZEzJ.jpg"
    asyncio.run(engine.dispose())


def test_fetch_cover_falls_back_to_placeholder(tmp_path, monkeypatch):
    """无B站链接或封面获取失败:回退到与任务管线一致的占位生图,不留空。"""
    engine, sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages", lambda config: [_message("cover-2", "# 无链接笔记")]
    )
    client = _client()
    data = client.post("/api/v1/email/fetch").json()
    article_id = data["imported"][0]["id"]

    async def load():
        async with sessions() as session:
            return await session.get(Article, article_id)

    article = asyncio.run(load())
    assert article.cover_image_url.startswith("https://coresg-normal.trae.ai/")
    asyncio.run(engine.dispose())
