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


@pytest.mark.parametrize('url,source', [
    ('https://blog.csdn.net/u/article/details/123', 'csdn'),
    ('https://www.cnblogs.com/u/p/123.html', 'cnblogs'),
    ('https://example.com/article', 'other'),
    ('https://youtu.be/BaW_jenozKc', 'youtube'),
])
def test_new_sources_submit_persist_and_filter_with_their_actual_source(refetch_client, monkeypatch, url, source):
    client, sessions = refetch_client
    async def fetch_article(*args):
        return dict(PAYLOAD)
    async def fetch_video(*args):
        return {'title': '真实视频正文', 'transcript_text': '完整的视频文稿。', 'description': '', 'uploader': '作者', 'cover_image_url': ''}
    async def notes(*args):
        return '# 视频笔记\n\n完整的视频文稿。'
    monkeypatch.setattr(task_service, 'fetch_article_content', fetch_article)
    monkeypatch.setattr(task_service, 'fetch_video_content', fetch_video)
    monkeypatch.setattr(task_service, 'generate_video_notes', notes)
    response = client.post('/api/v1/tasks/submit', json={'url': url})
    assert response.status_code == 200
    task = client.get(f"/api/v1/tasks/{response.json()['task_id']}/status").json()
    assert task['status'] == 'completed'
    article_id = task['article_id']
    article = client.get('/api/v1/articles/' + article_id).json()
    assert article['source_type'] == source
    assert '文稿' in article['content_md'] if source == 'youtube' else '正文' in article['content_md']
    assert client.get('/api/v1/articles/stats').json()['sources'][source] >= 1


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
    assert saved['created_at'] == CREATED.replace(tzinfo=datetime.UTC).astimezone().isoformat()
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


def test_x_import_and_refetch_use_saved_provider_order(refetch_client, monkeypatch):
    """Changing the stored priority must affect both import and in-place refetch."""
    import json
    from app.services.fetchers import x_providers
    client, sessions = refetch_client
    url = 'https://x.com/author/status/123456789'
    async def prepare():
        async with sessions() as session:
            article = await session.get(Article, 'saved')
            article.original_url = url
            article.source_type = 'x'
            await session.commit()
        await settings_store.save_settings({'fetchProviderPriorities': json.dumps({'x': ['content_downloader', 'tikhub']})})
    asyncio.run(prepare())
    async def graphql(url, update_step, config):
        return {'payload': {'title': '新方法标题', 'tweet_text': '新方法获取的完整正文', 'author_name': '作者', 'cover_image_url': '', 'created_at': ''}}
    def unexpected_paid(*args):
        raise AssertionError('首选成功后不应访问 TikHub')
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', graphql)
    monkeypatch.setattr(task_service, 'fetch_tikhub_tweet', unexpected_paid)
    refetched = status(client, submit(client))
    assert refetched['status'] == 'completed'
    article = client.get('/api/v1/articles/saved').json()
    assert '新方法获取的完整正文' in article['content_md']
    assert '<!-- X_CONTENT_START -->' in article['content_md']
    assert article['account_name'] == '作者'
    assert article['category'] == 'C++' and article['is_starred'] and article['read_progress'] == 0.6
    response = client.post('/api/v1/tasks/submit', json={'url': url})
    imported = status(client, response.json()['task_id'])
    assert imported['status'] == 'completed'
    assert imported['article_id'] != 'saved'
    assert '新方法获取的完整正文' in imported['article']['content_md']


@pytest.mark.parametrize('succeed', [True, False])
def test_wechat_import_and_refetch_follow_priority_without_losing_saved_content(refetch_client, monkeypatch, succeed):
    import httpx
    import json
    from app.services.fetchers import article as article_fetcher
    client, sessions = refetch_client
    url = 'https://mp.weixin.qq.com/s/wechat-priority'
    async def prepare():
        async with sessions() as session:
            row = await session.get(Article, 'saved')
            row.original_url = url
            row.source_type = 'wechat'
            await session.commit()
        await settings_store.save_settings({'fetchProviderPriorities': json.dumps({'wechat': ['content_downloader', 'tikhub']})})
    asyncio.run(prepare())
    original_client = httpx.AsyncClient
    def handler(request):
        assert request.url.host == 'mp.weixin.qq.com'
        html = ('<meta property="og:title" content="微信新标题"><a id="js_name">新公众号</a>'
                '<div id="js_content"><p>重新获取的微信公众号正文。</p></div>') if succeed else '<html>环境异常</html>'
        return httpx.Response(200, text=html, headers={'Content-Type': 'text/html; charset=utf-8'})
    monkeypatch.setattr(article_fetcher.httpx, 'AsyncClient', lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(task_service, 'fetch_article_content', article_fetcher.fetch_article_content)
    def no_paid(*args):
        raise RuntimeError('测试环境 TikHub 不可用')
    monkeypatch.setattr(article_fetcher, 'fetch_wechat_article', no_paid)
    before = client.get('/api/v1/articles/saved').json()
    task = status(client, submit(client))
    current = client.get('/api/v1/articles/saved').json()
    if not succeed:
        assert task['status'] == 'failed'
        assert current == before
        return
    assert task['status'] == 'completed'
    assert current['title'] == '微信新标题' and current['account_name'] == '新公众号'
    assert '重新获取的微信公众号正文' in current['content_md']
    assert '<!-- HTML_CONTENT_START -->' in current['content_md']
    assert current['category'] == 'C++' and current['is_starred'] and current['read_progress'] == 0.6
    imported = client.post('/api/v1/tasks/submit', json={'url': url})
    new_task = status(client, imported.json()['task_id'])
    assert new_task['status'] == 'completed' and new_task['article_id'] != 'saved'
    assert new_task['article']['source_type'] == 'wechat'


def test_cli_article_refetch_renders_rich_json_without_original_page(refetch_client, monkeypatch, tmp_path):
    import json
    import sys
    from app.services.fetchers import x_twitter_cli as cli
    from app.config import settings
    client, sessions = refetch_client
    monkeypatch.setattr(settings, 'MEDIA_DIR', str(tmp_path / 'media'))
    url = 'https://x.com/author/status/123456789'
    async def prepare():
        async with sessions() as session:
            row = await session.get(Article, 'saved')
            row.original_url = url
            row.source_type = 'x'
            await session.commit()
        await settings_store.save_settings({'fetchProviderPriorities': json.dumps({'x': ['twitter_cli', 'tikhub', 'content_downloader']})})
    asyncio.run(prepare())
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'test-auth')
    monkeypatch.setenv('TWITTER_CT0', 'test-ct0')
    monkeypatch.setattr(cli, '_twitter_command', lambda config=None: '/test/twitter')
    monkeypatch.setattr(cli, '_twitter_python', lambda command: sys.executable)
    raw = {'rest_id': '123456789', 'legacy': {'full_text': 'https://x.com/i/article/999'},
           'article': {'article_results': {'result': {'title': 'CLI 重新获取的长文', 'content_state': {'blocks': [
               {'type': 'unstyled', 'text': '完整长文正文', 'inlineStyleRanges': [{'offset': 0, 'length': 2, 'style': 'BOLD'}]},
           ]}}}}}
    class Process:
        returncode = 0
        async def communicate(self):
            return json.dumps({'tweet_result': raw}).encode(), b''
    async def spawn(*args, **kwargs):
        return Process()
    async def page_unavailable(*args):
        raise RuntimeError('原页不可用')
    def no_paid(*args):
        raise AssertionError('CLI 成功后不应调用 TikHub')
    monkeypatch.setattr(cli.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(task_service, 'fetch_x_article_replica', page_unavailable)
    monkeypatch.setattr(task_service, 'fetch_tikhub_tweet', no_paid)
    task = status(client, submit(client))
    assert task['status'] == 'completed'
    article = task['article']
    assert article['title'] == 'CLI 重新获取的长文'
    assert '<strong>完整</strong>长文正文' in article['content_md']
    assert '"status": "complete"' in article['content_md']
    assert 'archive_url' not in article['content_md']
    assert article['category'] == 'C++' and article['is_starred'] and article['read_progress'] == .6


def test_article_list_detail_related_and_task_dates_have_server_offset(refetch_client):
    client, _ = refetch_client
    listing = client.get('/api/v1/articles').json()['data'][0]
    detail = client.get('/api/v1/articles/saved').json()
    assert listing['created_at'] == detail['created_at'] == CREATED.replace(tzinfo=datetime.UTC).astimezone().isoformat()
    assert listing['updated_at'] == detail['updated_at'] == UPDATED.replace(tzinfo=datetime.UTC).astimezone().isoformat()
    task = status(client, submit(client))
    tasks_list = client.get('/api/v1/tasks').json()['data']
    assert datetime.datetime.fromisoformat(task['created_at']).utcoffset() is not None
    assert tasks_list[0]['created_at'] == task['created_at']
    assert task['article']['created_at'] == detail['created_at']
    runtime_store.TASKS_DB.clear()
    restored = status(client, task['id'])
    assert restored['created_at'] == task['created_at']
    assert restored['article']['created_at'] == detail['created_at']


def test_new_submission_saves_utc_and_returns_local_time(refetch_client):
    client, sessions = refetch_client
    before = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    response = client.post('/api/v1/tasks/submit', json={'url': ORIGINAL_URL})
    task = status(client, response.json()['task_id'])
    after = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    assert task['status'] == 'completed'
    async def check():
        async with sessions() as session:
            saved = await session.get(Article, task['article_id'])
            assert before <= saved.created_at <= after
    asyncio.run(check())
    assert datetime.datetime.fromisoformat(task['created_at']).utcoffset() is not None
    assert task['article']['created_at'] == task['created_at']
