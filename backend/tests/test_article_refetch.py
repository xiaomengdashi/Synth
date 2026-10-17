"""Refetch must update the existing record only after a successful persistent save."""
import asyncio
import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Article, Note, Task
from app.routers import articles, tasks
from app.services import runtime_store, settings_store, task_service

ORIGINAL_URL = 'https://example.com/original'
CREATED = datetime.datetime(2026, 9, 1, 12)
UPDATED = datetime.datetime(2026, 9, 2, 12)
PAYLOAD = {'title': '重新获取的标题', 'extracted_md': '重新抓取的完整正文。', 'html_content': '',
           'cover_image_url': 'https://example.com/new.jpg', 'account_name': '新作者', 'publish_time': '2026-10-18'}


@pytest.fixture
def refetch_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'refetch.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(Article(id='saved', title='原标题', content_md='原正文', summary='原摘要',
                                original_url=ORIGINAL_URL, source_type='other', category='C++',
                                is_starred=True, read_progress=0.6, email_message_id='mail-id',
                                created_at=CREATED, updated_at=UPDATED))
            session.add(Note(id='note', article_id='saved', quote='原正文', note='保留笔记'))
            await session.commit()
    asyncio.run(prepare())

    async def database():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(settings_store, 'AsyncSessionLocal', sessions)
    monkeypatch.setattr(task_service, 'AsyncSessionLocal', sessions)
    monkeypatch.setattr(runtime_store, 'ARTICLES_DB', {'saved': {'id': 'saved', 'content_md': '原正文'}})
    monkeypatch.setattr(runtime_store, 'TASKS_DB', {})
    for module in (articles, task_service):
        monkeypatch.setattr(module, 'ARTICLES_DB', runtime_store.ARTICLES_DB)
    for module in (articles, tasks, task_service):
        monkeypatch.setattr(module, 'TASKS_DB', runtime_store.TASKS_DB)

    async def fetch(url, update_step, config):
        assert url == ORIGINAL_URL
        async with sessions() as session:
            assert (await session.get(Article, 'saved')).content_md == '原正文'
        assert runtime_store.ARTICLES_DB['saved']['content_md'] == '原正文'
        update_step('正在重新抓取正文')
        return dict(PAYLOAD)
    monkeypatch.setattr(task_service, 'fetch_article_content', fetch)
    app = FastAPI()
    app.include_router(articles.router, prefix='/api/v1/articles')
    app.include_router(tasks.router, prefix='/api/v1/tasks')
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    asyncio.run(engine.dispose())


def submit(client):
    response = client.post('/api/v1/articles/saved/refetch')
    assert response.status_code == 202
    return response.json()['task_id']


def status(client, task_id):
    return client.get(f'/api/v1/tasks/{task_id}/status').json()


def test_refetch_updates_same_article_preserving_reader_metadata_and_notes(refetch_client):
    client, sessions = refetch_client
    before = client.get('/api/v1/articles/saved')
    task_id = submit(client)
    task = status(client, task_id)
    assert task['status'] == 'completed'
    assert task['article_id'] == task['article']['id'] == 'saved'
    assert task['article']['is_starred'] is True
    assert task['article']['category'] == 'C++'
    assert task['article']['read_progress'] == 0.6
    current = client.get('/api/v1/articles/saved', headers={'If-None-Match': before.headers['etag']})
    assert current.status_code == 200
    saved = current.json()
    assert saved['title'] == PAYLOAD['title']
    assert PAYLOAD['extracted_md'] in saved['content_md']
    assert saved['original_url'] == ORIGINAL_URL
    assert saved['created_at'] == CREATED.isoformat()
    assert saved['updated_at'] != UPDATED.isoformat()
    assert saved['email_message_id'] == 'mail-id'
    assert saved['account_name'] == PAYLOAD['account_name']
    assert current.headers['etag'] != before.headers['etag']

    async def verify():
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Article)) == 1
            assert (await session.get(Note, 'note')).note == '保留笔记'
            assert (await session.get(Task, task_id)).status == 'completed'
    asyncio.run(verify())
    assert runtime_store.ARTICLES_DB['saved']['content_md'] == saved['content_md']


def test_upstream_failure_keeps_original_content_and_cache(refetch_client, monkeypatch):
    client, _ = refetch_client
    before = client.get('/api/v1/articles/saved')

    async def fail(*args):
        raise RuntimeError('上游暂时不可用')
    monkeypatch.setattr(task_service, 'fetch_article_content', fail)
    task = status(client, submit(client))
    assert task['status'] == 'failed'
    assert task['article_id'] == 'saved'
    assert '上游暂时不可用' in task['current_step']
    after = client.get('/api/v1/articles/saved')
    assert after.json() == before.json()
    assert after.headers['etag'] == before.headers['etag']
    assert runtime_store.ARTICLES_DB['saved']['content_md'] == '原正文'


def test_commit_failure_does_not_publish_new_content_or_completed_status(refetch_client, monkeypatch):
    client, _ = refetch_client
    commit = AsyncSession.commit

    async def fail_content_save(session):
        if any(isinstance(row, Article) and row.title == PAYLOAD['title'] for row in session.identity_map.values()):
            raise RuntimeError('模拟保存失败')
        return await commit(session)
    monkeypatch.setattr(AsyncSession, 'commit', fail_content_save)
    task = status(client, submit(client))
    assert task['status'] == 'failed'
    assert client.get('/api/v1/articles/saved').json()['content_md'] == '原正文'
    assert runtime_store.ARTICLES_DB['saved']['content_md'] == '原正文'


def test_duplicate_request_reuses_persistent_active_task(refetch_client, monkeypatch):
    client, _ = refetch_client
    scheduled = []

    async def pause(*args):
        scheduled.append(args)
    monkeypatch.setattr(articles, 'process_task', pause, raising=False)
    first = submit(client)
    runtime_store.TASKS_DB.clear()
    second = submit(client)
    assert second == first
    assert len(scheduled) == 1
    assert client.get('/api/v1/tasks').json()['total'] == 1


def test_refetch_requires_admin_and_handles_missing_article(refetch_client):
    client, _ = refetch_client
    asyncio.run(settings_store.set_admin_token_hash(settings_store.hash_admin_token('secret')))
    assert client.post('/api/v1/articles/saved/refetch').status_code == 401
    assert client.post('/api/v1/articles/saved/refetch', headers={'X-Admin-Token': 'wrong'}).status_code == 401
    assert client.post('/api/v1/articles/missing/refetch', headers={'X-Admin-Token': 'secret'}).status_code == 404
    assert client.post('/api/v1/articles/saved/refetch', headers={'X-Admin-Token': 'secret'}).status_code == 202


def test_deleted_article_is_not_recreated_by_running_refetch(refetch_client, monkeypatch):
    client, sessions = refetch_client

    async def delete_during_fetch(*args):
        async with sessions() as session:
            await session.delete(await session.get(Article, 'saved'))
            await session.commit()
        runtime_store.ARTICLES_DB.pop('saved', None)
        return dict(PAYLOAD)
    monkeypatch.setattr(task_service, 'fetch_article_content', delete_during_fetch)
    task = status(client, submit(client))
    assert task['status'] == 'failed'
    assert client.get('/api/v1/articles/saved').status_code == 404
    assert client.get('/api/v1/articles').json()['total'] == 0


def test_refetch_rejects_non_http_original_url(refetch_client):
    client, sessions = refetch_client

    async def change_url():
        async with sessions() as session:
            row = await session.get(Article, 'saved')
            row.original_url = 'file:///tmp/article.html'
            await session.commit()
    asyncio.run(change_url())
    assert client.post('/api/v1/articles/saved/refetch').status_code == 400
    assert client.get('/api/v1/tasks').json()['total'] == 0
