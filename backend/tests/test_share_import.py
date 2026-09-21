import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Article
from app.routers import tasks
from app.services import runtime_store, task_service


@pytest.fixture
def share_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'share.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def database():
        async with sessions() as session:
            yield session

    async def no_external_fetch(*args):
        pass

    monkeypatch.setattr(task_service, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(tasks, "process_task", no_external_fetch)
    monkeypatch.setattr(runtime_store, "TASKS_DB", {})
    monkeypatch.setattr(tasks, "TASKS_DB", runtime_store.TASKS_DB)
    app = FastAPI()
    app.include_router(tasks.router, prefix="/api/v1/tasks")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    asyncio.run(engine.dispose())


def test_shared_text_creates_a_persistent_task_without_phone_config(share_client):
    client, _ = share_client
    response = client.post("/api/v1/tasks/share", json={
        "text": "值得读的一篇长文：https://x.com/Author/status/123456789?s=46&t=tracking",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["original_url"] == "https://x.com/author/status/123456789"
    assert data["status"] == "pending"
    records = client.get("/api/v1/tasks").json()["data"]
    assert len(records) == 1
    assert records[0]["id"] == data["task_id"]


def test_repeated_share_reuses_task_across_url_aliases(share_client):
    client, _ = share_client
    first = client.post("/api/v1/tasks/share", json={"url": "https://twitter.com/Author/status/123456789?s=20"})
    second = client.post("/api/v1/tasks/share", json={"text": "https://mobile.x.com/i/web/status/123456789"})
    assert first.status_code == second.status_code == 200
    assert first.json()["task_id"] == second.json()["task_id"]
    assert second.json()["reused"] is True
    assert len(client.get("/api/v1/tasks").json()["data"]) == 1


def test_saved_article_is_reused_even_with_old_tracking_parameters(share_client):
    client, sessions = share_client

    async def save():
        async with sessions() as session:
            session.add(Article(id="existing", title="已保存", summary="正文", content_md="正文",
                                original_url="https://twitter.com/author/status/123456789?s=20",
                                source_type="x"))
            await session.commit()

    asyncio.run(save())
    response = client.post("/api/v1/tasks/share", json={"url": "https://x.com/author/status/123456789"})
    assert response.status_code == 200
    assert response.json()["article_id"] == "existing"
    assert response.json()["status"] == "completed"
    assert client.get("/api/v1/tasks").json()["data"] == []


@pytest.mark.parametrize("payload", [
    {}, {"text": "没有文章链接"}, {"url": "https://x.com.evil.example/author/status/123"},
    {"url": "https://x.com@127.0.0.1/author/status/123"},
    {"url": "http://127.0.0.1:8000/"}, {"url": "https://x.com/author"},
    {"text": "https://x.com/a/status/123 https://x.com/b/status/456"},
])
def test_invalid_or_ambiguous_shares_do_not_create_tasks(share_client, payload):
    client, _ = share_client
    response = client.post("/api/v1/tasks/share", json=payload)
    assert response.status_code == 400
    assert client.get("/api/v1/tasks").json()["data"] == []


def test_direct_x_article_link_is_accepted(share_client):
    client, _ = share_client
    response = client.post("/api/v1/tasks/share", json={"url": "https://x.com/i/article/987654321"})
    assert response.status_code == 200
    assert response.json()["original_url"] == "https://x.com/i/article/987654321"


def test_direct_article_fetch_does_not_depend_on_tweet_mirror(share_client, monkeypatch):
    _, sessions = share_client
    task_id = "direct-article"
    task_service.TASKS_DB[task_id] = {"id": task_id, "created_at": "2026-09-22T00:00:00"}

    def unavailable_mirror(url):
        raise AssertionError("A direct article must not be sent to a tweet-only mirror")

    async def article_fetch(url, update_step):
        assert url == "https://x.com/i/article/987654321"
        return {"title": "长文标题", "content_md": "完整长文正文", "cover_image_url": ""}

    monkeypatch.setattr(task_service, "fetch_tweet_data", unavailable_mirror)
    monkeypatch.setattr(task_service, "fetch_x_article_via_twitter_cli", article_fetch)
    asyncio.run(task_service.create_task_record(task_id, "https://x.com/i/article/987654321", "2026-09-22T00:00:00"))
    asyncio.run(task_service.process_task(task_id, "https://x.com/i/article/987654321", tasks.ModelConfig()))
    assert task_service.TASKS_DB[task_id]["status"] == "completed"
    assert "完整长文正文" in task_service.TASKS_DB[task_id]["article"]["content_md"]
    task_service.TASKS_DB.pop(task_id, None)
