import asyncio
import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Article, Note
from app.routers import articles, notes
from app.services import runtime_store, settings_store


@pytest.fixture
def notes_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'notes.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def database():
        async with sessions() as session:
            yield session

    # articles.py 在 import 时已绑定 ARTICLES_DB 名称,隔离内存兜底须 patch 使用方模块属性
    monkeypatch.setattr(runtime_store, "ARTICLES_DB", {})
    monkeypatch.setattr(articles, "ARTICLES_DB", runtime_store.ARTICLES_DB)
    # require_admin 链路读 settings 表:patch AsyncSessionLocal 指向测试库
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    app = FastAPI()
    app.include_router(articles.router, prefix="/api/v1/articles")
    app.include_router(notes.router, prefix="/api/v1/notes")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    asyncio.run(engine.dispose())


def seed_article(sessions, article_id, title="文章"):
    async def save():
        async with sessions() as session:
            session.add(Article(
                id=article_id,
                title=title,
                summary="摘要",
                content_md="正文",
                original_url=f"https://example.com/{article_id}",
                source_type="other",
            ))
            await session.commit()

    asyncio.run(save())


def seed_note(sessions, note_id, article_id, quote, note="笔记", created_at=None):
    async def save():
        async with sessions() as session:
            session.add(Note(
                id=note_id,
                article_id=article_id,
                quote=quote,
                note=note,
                prefix="前",
                suffix="后",
                created_at=created_at or datetime.datetime(2026, 10, 1, 12, 0, 0),
            ))
            await session.commit()

    asyncio.run(save())


def set_admin_token():
    asyncio.run(settings_store.set_admin_token_hash(settings_store.hash_admin_token("secret")))


def test_create_returns_full_fields_and_lists_per_article(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1")
    seed_article(sessions, "a2")
    seed_note(sessions, "n1", "a1", "旧划线", created_at=datetime.datetime(2026, 10, 1, 8, 0, 0))

    response = client.post("/api/v1/notes", json={
        "article_id": "a1", "quote": "新划线", "note": "新笔记", "prefix": "前文", "suffix": "后文",
    })
    assert response.status_code == 200
    row = response.json()
    assert set(row) >= {"id", "article_id", "quote", "note", "prefix", "suffix", "created_at"}
    assert row["article_id"] == "a1"
    assert row["quote"] == "新划线"
    assert row["prefix"] == "前文"
    assert row["suffix"] == "后文"
    # created_at 是 UTC naive,JSON 必须补 Z 明示 UTC,否则浏览器按本地时区解析偏移数小时
    assert row["created_at"].endswith("Z")

    listing = client.get("/api/v1/notes", params={"article_id": "a1"}).json()
    assert listing["total"] == 2
    # 升序=阅读顺序:旧划线在前
    assert [item["quote"] for item in listing["data"]] == ["旧划线", "新划线"]
    assert all(item["created_at"].endswith("Z") for item in listing["data"])
    # 只含本文笔记,不混入其他文章
    assert all(item["article_id"] == "a1" for item in listing["data"])
    assert client.get("/api/v1/notes", params={"article_id": "a2"}).json()["total"] == 0


def test_create_note_404_for_missing_article(notes_client):
    client, _ = notes_client
    response = client.post("/api/v1/notes", json={
        "article_id": "missing", "quote": "划线", "note": "笔记",
    })
    assert response.status_code == 404


def test_duplicate_quote_409_same_article_but_ok_cross_article(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1")
    seed_article(sessions, "a2")
    payload = {"article_id": "a1", "quote": "同一段", "note": "第一条"}
    assert client.post("/api/v1/notes", json=payload).status_code == 200
    # 同文章同 quote 精确重复 → 409(客户端前置拦截外的二道防线)
    repeat = client.post("/api/v1/notes", json={**payload, "note": "第二条"})
    assert repeat.status_code == 409
    assert repeat.json()["detail"] == "这段划线已有笔记"
    # 不同文章同 quote 不算重复
    cross = client.post("/api/v1/notes", json={**payload, "article_id": "a2"})
    assert cross.status_code == 200


def test_validation_rejects_empty_note_and_overlong_quote(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1")
    assert client.post("/api/v1/notes", json={
        "article_id": "a1", "quote": "划线", "note": "",
    }).status_code == 422
    assert client.post("/api/v1/notes", json={
        "article_id": "a1", "quote": "字" * 2001, "note": "笔记",
    }).status_code == 422
    # 读者列表缺 article_id → 422
    assert client.get("/api/v1/notes").status_code == 422


def test_reader_listing_stays_open_without_token(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1")
    seed_note(sessions, "n1", "a1", "划线")
    # 设令牌后读者级接口依旧无鉴权开放(star/progress 同口径)
    set_admin_token()
    response = client.get("/api/v1/notes", params={"article_id": "a1"})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_admin_all_requires_token_and_joins_title(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1", title="带标题文章")
    seed_note(sessions, "n1", "a1", "划线")
    set_admin_token()
    # 无 header → 401
    assert client.get("/api/v1/notes/all").status_code == 401
    # 带 header → 200 且行含 article_title
    response = client.get("/api/v1/notes/all", headers={"X-Admin-Token": "secret"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["data"][0]["article_title"] == "带标题文章"
    assert payload["data"][0]["quote"] == "划线"
    assert payload["data"][0]["created_at"].endswith("Z")


def test_admin_all_pagination_and_beyond_end_offset(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1")
    for index in range(3):
        seed_note(sessions, f"n{index}", "a1", f"划线{index}",
                  created_at=datetime.datetime(2026, 10, 1, 9, index, 0))
    set_admin_token()
    headers = {"X-Admin-Token": "secret"}

    first = client.get("/api/v1/notes/all", params={"limit": 2, "offset": 0}, headers=headers).json()
    assert first["total"] == 3
    assert len(first["data"]) == 2
    # 倒序:最新的划线2在前
    assert first["data"][0]["quote"] == "划线2"

    second = client.get("/api/v1/notes/all", params={"limit": 2, "offset": 2}, headers=headers).json()
    assert len(second["data"]) == 1
    assert second["data"][0]["quote"] == "划线0"

    # offset 越界空页:窗口 COUNT 拿不到行,必须回退独立 COUNT(对齐 e25915b 回归)
    beyond = client.get("/api/v1/notes/all", params={"limit": 2, "offset": 20}, headers=headers).json()
    assert beyond["data"] == []
    assert beyond["total"] == 3


def test_admin_all_filters_by_article_with_stable_options(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1", title="文章一")
    seed_article(sessions, "b1", title="文章二")
    seed_article(sessions, "c1", title="无笔记文章")
    seed_note(sessions, "n1", "a1", "划线一")
    seed_note(sessions, "n2", "b1", "划线二")
    set_admin_token()

    payload = client.get(
        "/api/v1/notes/all", params={"article_id": "a1"}, headers={"X-Admin-Token": "secret"},
    ).json()
    assert payload["total"] == 1
    assert [row["quote"] for row in payload["data"]] == ["划线一"]
    # articles 选项为全表有笔记的文章(c1 无笔记不出现),不受当前筛选影响
    option_ids = sorted(item["id"] for item in payload["articles"])
    assert option_ids == ["a1", "b1"]


def test_delete_note_auth_and_missing(notes_client):
    client, sessions = notes_client
    seed_article(sessions, "a1")
    seed_note(sessions, "n1", "a1", "划线")
    set_admin_token()

    assert client.delete("/api/v1/notes/n1").status_code == 401
    ok = client.delete("/api/v1/notes/n1", headers={"X-Admin-Token": "secret"})
    assert ok.status_code == 200
    assert ok.json() == {"status": "success"}
    assert client.delete("/api/v1/notes/n1", headers={"X-Admin-Token": "secret"}).status_code == 404
    assert client.get("/api/v1/notes", params={"article_id": "a1"}).json()["total"] == 0


def test_deleting_article_cleans_notes_both_ways(notes_client):
    client, sessions = notes_client
    # 单删:先建笔记,DELETE 文章后笔记清空
    seed_article(sessions, "a1")
    seed_note(sessions, "n1", "a1", "划线一")
    set_admin_token()
    headers = {"X-Admin-Token": "secret"}
    assert client.delete("/api/v1/articles/a1", headers=headers).status_code == 200
    assert client.get("/api/v1/notes", params={"article_id": "a1"}).json()["total"] == 0

    # 批量删:响应带 notes_deleted 计数,笔记一并清理
    seed_article(sessions, "a2")
    seed_article(sessions, "a3")
    seed_note(sessions, "n2", "a2", "划线二")
    seed_note(sessions, "n3", "a2", "划线三")
    seed_note(sessions, "n4", "a3", "划线四")
    batch = client.post("/api/v1/articles/batch-delete", json={"ids": ["a2", "a3"]}, headers=headers)
    assert batch.status_code == 200
    assert batch.json()["notes_deleted"] == 3
    assert client.get("/api/v1/notes", params={"article_id": "a2"}).json()["total"] == 0
    assert client.get("/api/v1/notes", params={"article_id": "a3"}).json()["total"] == 0
