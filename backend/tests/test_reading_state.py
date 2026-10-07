import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Article
from app.routers import articles
from app.services import runtime_store


@pytest.fixture
def reading_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reading.db'}")
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
    app = FastAPI()
    app.include_router(articles.router, prefix="/api/v1/articles")
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


def test_star_toggle_filters_list_and_counts(reading_client):
    client, sessions = reading_client
    seed_article(sessions, "a1")
    seed_article(sessions, "a2")

    # 无头 PATCH 收藏成功
    response = client.patch("/api/v1/articles/a1/star", json={"starred": True})
    assert response.status_code == 200
    assert response.json() == {"starred": True}

    # 列表 ?starred=1 只剩该篇
    starred_list = client.get("/api/v1/articles?starred=1").json()
    assert starred_list["total"] == 1
    assert [row["id"] for row in starred_list["data"]] == ["a1"]
    assert starred_list["data"][0]["is_starred"] is True

    # stats 给出收藏计数
    stats = client.get("/api/v1/articles/stats").json()
    assert stats["starred"] == 1

    # 再点取消收藏恢复原状
    response = client.patch("/api/v1/articles/a1/star", json={"starred": False})
    assert response.status_code == 200
    assert response.json() == {"starred": False}
    assert client.get("/api/v1/articles?starred=1").json()["total"] == 0
    assert client.get("/api/v1/articles/stats").json()["starred"] == 0


def test_progress_clamps_into_range_and_stays_monotonic(reading_client):
    client, sessions = reading_client
    seed_article(sessions, "a1")

    # clamp:-1 → 0,1.5 → 1
    assert client.put("/api/v1/articles/a1/progress", json={"progress": -1}).json() == {"progress": 0}
    assert client.put("/api/v1/articles/a1/progress", json={"progress": 1.5}).json() == {"progress": 1}

    # 单调:新文章推到 0.9 后回落 0.4,仍保留 0.9
    seed_article(sessions, "b1")
    assert client.put("/api/v1/articles/b1/progress", json={"progress": 0.9}).json() == {"progress": 0.9}
    assert client.put("/api/v1/articles/b1/progress", json={"progress": 0.4}).json() == {"progress": 0.9}

    detail = client.get("/api/v1/articles/b1").json()
    assert detail["read_progress"] == 0.9


def test_star_and_progress_return_404_for_missing_article(reading_client):
    client, _ = reading_client
    assert client.patch("/api/v1/articles/missing/star", json={"starred": True}).status_code == 404
    assert client.put("/api/v1/articles/missing/progress", json={"progress": 0.5}).status_code == 404


def test_list_rows_carry_reading_fields(reading_client):
    client, sessions = reading_client
    seed_article(sessions, "a1")
    rows = client.get("/api/v1/articles").json()["data"]
    assert len(rows) == 1
    assert rows[0]["is_starred"] is False
    assert rows[0]["read_progress"] == 0.0


def test_detail_etag_changes_with_reading_state(reading_client):
    client, sessions = reading_client
    seed_article(sessions, "a1")

    first = client.get("/api/v1/articles/a1")
    etag = first.headers["ETag"]

    # 未变时携带 If-None-Match 重验证命中 304
    cached = client.get("/api/v1/articles/a1", headers={"If-None-Match": etag})
    assert cached.status_code == 304

    # 收藏翻转后 ETag 必须变化:重验证得 200 且带回新阅读态
    client.patch("/api/v1/articles/a1/star", json={"starred": True})
    refreshed = client.get("/api/v1/articles/a1", headers={"If-None-Match": etag})
    assert refreshed.status_code == 200
    assert refreshed.json()["is_starred"] is True

    # 进度写入同理:单调更新后旧 ETag 不再命中
    etag_after_star = refreshed.headers["ETag"]
    client.put("/api/v1/articles/a1/progress", json={"progress": 0.5})
    progressed = client.get("/api/v1/articles/a1", headers={"If-None-Match": etag_after_star})
    assert progressed.status_code == 200
    assert progressed.json()["read_progress"] == 0.5

    # 单调无变化的进度写(0.3 < 0.5)不改值,新 ETag 继续命中 304
    etag_after_progress = progressed.headers["ETag"]
    client.put("/api/v1/articles/a1/progress", json={"progress": 0.3})
    assert client.get("/api/v1/articles/a1", headers={"If-None-Match": etag_after_progress}).status_code == 304
