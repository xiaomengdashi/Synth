import asyncio
import datetime

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
        lambda config, days=30: [_message("msg-1", "# 网络原理\n\nhttps://b23.tv/abc"), _message("msg-2", None)],
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
        email_import, "fetch_whitelisted_messages", lambda config, days=30: [_message("msg-1", "# 标题\n\n正文")]
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

    def raise_no_whitelist(config, days=30):
        raise EmailFetchError("请先配置发件人白名单，再拉取邮件。")

    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", raise_no_whitelist)
    response = _client().post("/api/v1/email/fetch")
    assert response.status_code == 400
    assert "白名单" in response.json()["detail"]
    asyncio.run(engine.dispose())


def test_test_endpoint_reports_recent_count(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", lambda config, days=30: [_message("m1", "# t")])
    data = _client().post("/api/v1/email/test").json()
    assert data == {"ok": True, "recent_count": 1}
    asyncio.run(engine.dispose())


def test_fetch_covers_real_bilibili_video(tmp_path, monkeypatch):
    """正文带B站链接:取官方真实封面并本地化。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config, days=30: [_message("cover-1", "# 封面\n\nhttps://www.bilibili.com/video/BV17x6hYZEzJ")],
    )
    monkeypatch.setattr(email_import, "_fetch_bilibili_official_view", lambda bvid: {"pic": "https://i0.hdslb.com/bfs/x.jpg"})
    monkeypatch.setattr(email_import, "_localize_bilibili_cover", lambda pic, bvid: f"/media/bilibili/{bvid}.jpg")
    client = _client()
    data = client.post("/api/v1/email/fetch").json()
    assert data["imported"][0]["id"] in ARTICLES_DB
    assert ARTICLES_DB[data["imported"][0]["id"]]["cover_image_url"] == "/media/bilibili/BV17x6hYZEzJ.jpg"
    asyncio.run(engine.dispose())


def test_fetch_cover_empty_without_reference(tmp_path, monkeypatch):
    """无B站引用或获取失败:封面留空走前端来源色块兜底,禁止任何占位图。"""
    engine, sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages", lambda config, days=30: [_message("cover-2", "# 无链接笔记")]
    )
    client = _client()
    data = client.post("/api/v1/email/fetch").json()
    article_id = data["imported"][0]["id"]

    async def load():
        async with sessions() as session:
            return await session.get(Article, article_id)

    article = asyncio.run(load())
    assert article.cover_image_url == ""
    asyncio.run(engine.dispose())


def test_fetch_subject_bvid_resolves_url_and_cover(tmp_path, monkeypatch):
    """正文无链接但邮件主题带裸 BV 号:还原 original_url 并取真实封面。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    message = EmailMessageData(
        message_id="cover-3", from_addr="milky@example.com",
        subject="《标题》文稿 | BV191Yj6HEAn", date="2026-10-06 09:00",
        md_attachments=[{"filename": "n.md", "content": "# 标题\n\n正文没有链接"}],
    )
    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", lambda config, days=30: [message])
    monkeypatch.setattr(email_import, "_fetch_bilibili_official_view", lambda bvid: {"pic": "https://i0.hdslb.com/x.jpg"})
    monkeypatch.setattr(email_import, "_localize_bilibili_cover", lambda pic, bvid: f"/media/bilibili/{bvid}.jpg")
    data = _client().post("/api/v1/email/fetch").json()
    article_id = data["imported"][0]["id"]
    article = ARTICLES_DB[article_id]
    assert article["original_url"] == "https://www.bilibili.com/video/BV191Yj6HEAn"
    assert article["cover_image_url"] == "/media/bilibili/BV191Yj6HEAn.jpg"
    asyncio.run(engine.dispose())


def test_refetch_after_delete_reimports(tmp_path, monkeypatch):
    """文章被删后重拉应重新入库,而不是被去重清单拦住。"""
    from sqlalchemy import delete as sa_delete

    engine, sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages", lambda config, days=30: [_message("msg-r", "# 删了重拉")]
    )
    client = _client()
    first = client.post("/api/v1/email/fetch").json()
    assert len(first["imported"]) == 1
    article_id = first["imported"][0]["id"]

    async def remove():
        async with sessions() as session:
            await session.execute(sa_delete(Article).where(Article.id == article_id))
            await session.commit()

    asyncio.run(remove())

    second = client.post("/api/v1/email/fetch").json()
    assert len(second["imported"]) == 1
    assert second["imported"][0]["id"] != article_id
    assert second["skipped"] == []
    asyncio.run(engine.dispose())


def test_fetch_skips_when_article_still_exists(tmp_path, monkeypatch):
    """文章还在时,去重照常生效。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages", lambda config, days=30: [_message("msg-keep", "# 保留")]
    )
    client = _client()
    assert len(client.post("/api/v1/email/fetch").json()["imported"]) == 1
    second = client.post("/api/v1/email/fetch").json()
    assert second["imported"] == []
    assert second["skipped"] == [{"subject": "B站笔记", "reason": "已导入过，跳过"}]
    asyncio.run(engine.dispose())


def test_fetch_and_test_accept_days_parameter(tmp_path, monkeypatch):
    """拉取/测试连接支持 days 参数,缺省 30,超界拒绝。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    captured = {}

    def fake_fetch(config, days=30):
        captured["days"] = days
        return [_message("d1", "# t")]

    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", fake_fetch)
    client = _client()

    assert len(client.post("/api/v1/email/fetch", json={"days": 90}).json()["imported"]) == 1
    assert captured["days"] == 90
    client.post("/api/v1/email/test", json={"days": 180})
    assert captured["days"] == 180
    client.post("/api/v1/email/fetch")
    assert captured["days"] == 7
    assert client.post("/api/v1/email/fetch", json={"days": 0}).status_code == 422
    assert client.post("/api/v1/email/fetch", json={"days": 4000}).status_code == 422
    asyncio.run(engine.dispose())


def test_import_uses_email_date_as_created_at(tmp_path, monkeypatch):
    """列表按 created_at 排序/显示,邮件文章的 created_at 应是收件时间而非入库时刻。"""
    engine, sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config, days=30: [_message("msg-time", "# 时间测试")],
    )
    client = _client()
    article_id = client.post("/api/v1/email/fetch").json()["imported"][0]["id"]

    async def load():
        async with sessions() as session:
            return await session.get(Article, article_id)

    article = asyncio.run(load())
    # 旧版无偏移的邮件日期按服务器本地时间解释，持久化为 UTC。
    assert article.created_at == datetime.datetime(2026, 10, 4, 10, 30).astimezone(datetime.UTC).replace(tzinfo=None)
    assert article.publish_time == "2026-10-04 10:30"
    asyncio.run(engine.dispose())


def test_fetch_cover_falls_back_to_tikhub(tmp_path, monkeypatch):
    """海外服务器官方接口 412 风控时,降级 TikHub first_frame 拿封面。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config, days=30: [_message("cover-tk", "# TikHub封面\n\nhttps://www.bilibili.com/video/BV17x6hYZEzJ")],
    )

    def raise_412(bvid):
        raise RuntimeError("HTTP 412")

    monkeypatch.setattr(email_import, "_fetch_bilibili_official_view", raise_412)
    monkeypatch.setattr(email_import, "_fetch_cover_via_tikhub", lambda bvid, config: "http://i1.hdslb.com/bfs/storyff/cover.jpg")
    monkeypatch.setattr(email_import, "_localize_bilibili_cover", lambda pic, bvid: f"/media/bilibili/{bvid}.jpg")
    data = _client().post("/api/v1/email/fetch").json()
    article = ARTICLES_DB[data["imported"][0]["id"]]
    assert article["cover_image_url"] == "/media/bilibili/BV17x6hYZEzJ.jpg"
    asyncio.run(engine.dispose())


def test_fetch_cover_empty_when_both_sources_fail(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config, days=30: [_message("cover-none", "# 无封面\n\nhttps://www.bilibili.com/video/BV1x")]
    )
    monkeypatch.setattr(email_import, "_fetch_bilibili_official_view", lambda bvid: (_ for _ in ()).throw(RuntimeError("412")))
    monkeypatch.setattr(email_import, "_fetch_cover_via_tikhub", lambda bvid, config: "")
    data = _client().post("/api/v1/email/fetch").json()
    assert ARTICLES_DB[data["imported"][0]["id"]]["cover_image_url"] == ""
    asyncio.run(engine.dispose())


def test_fetch_cover_falls_back_to_mobile_page(tmp_path, monkeypatch):
    """海外服务器官方接口 412 时,优先走 m 站 og:image(免费),不动 TikHub。"""
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config, days=30: [_message("cover-m", "# m站封面\n\nhttps://www.bilibili.com/video/BV17x6hYZEzJ")],
    )
    monkeypatch.setattr(email_import, "_fetch_bilibili_official_view", lambda bvid: (_ for _ in ()).throw(RuntimeError("412")))
    called = {"tikhub": 0}
    monkeypatch.setattr(email_import, "_fetch_cover_via_tikhub", lambda bvid, config: (called.__setitem__("tikhub", 1), "")[1])
    monkeypatch.setattr(email_import, "_fetch_cover_from_mobile_page", lambda bvid: "https://i0.hdslb.com/bfs/archive/cover.jpg@1200w_630h")
    monkeypatch.setattr(email_import, "_localize_bilibili_cover", lambda pic, bvid: f"/media/bilibili/{bvid}.jpg")
    data = _client().post("/api/v1/email/fetch").json()
    article = ARTICLES_DB[data["imported"][0]["id"]]
    assert article["cover_image_url"] == "/media/bilibili/BV17x6hYZEzJ.jpg"
    assert called["tikhub"] == 0  # m 站命中就不该再碰 TikHub
    asyncio.run(engine.dispose())
