"""Priority changes must persist, validate providers, and govern X fallback."""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.routers import config
from app.services import settings_store


@pytest.fixture
def priority_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'settings.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(prepare())
    monkeypatch.setattr(settings_store, 'AsyncSessionLocal', sessions)
    app = FastAPI()
    app.include_router(config.router, prefix='/api/v1/config')
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


def test_priority_roundtrip_and_other_settings_do_not_reset_it(priority_client):
    client = priority_client
    response = client.get('/api/v1/config/fetch-priorities')
    assert response.status_code == 200
    assert response.json()['priorities']['x'] == ['tikhub', 'x_graphql', 'twitter_cli']
    response = client.put('/api/v1/config/fetch-priorities', json={
        'priorities': {'x': ['x_graphql', 'tikhub', 'twitter_cli']},
    })
    assert response.status_code == 200
    assert response.json()['priorities']['x'] == ['x_graphql', 'tikhub', 'twitter_cli']
    assert client.post('/api/v1/config', json={'modelName': 'test'}).status_code == 200
    assert client.get('/api/v1/config/fetch-priorities').json()['priorities']['x'] == ['x_graphql', 'tikhub', 'twitter_cli']
    runtime = asyncio.run(config.get_runtime_config())
    assert json.loads(runtime['fetchProviderPriorities'])['x'] == ['x_graphql', 'tikhub', 'twitter_cli']


@pytest.mark.parametrize('priorities', [
    {'x': ['unknown', 'tikhub']}, {'x': ['tikhub', 'tikhub']}, {'x': []},
    {'wechat': ['direct', 'tikhub']}, {'unknown': ['tikhub']},
])
def test_invalid_priority_is_rejected_without_overwriting(priority_client, priorities):
    client = priority_client
    response = client.put('/api/v1/config/fetch-priorities', json={'priorities': priorities})
    assert response.status_code == 422
    assert client.get('/api/v1/config/fetch-priorities').json()['priorities']['x'] == ['tikhub', 'x_graphql', 'twitter_cli']


def test_priority_admin_auth(priority_client):
    client = priority_client
    asyncio.run(settings_store.set_admin_token_hash(settings_store.hash_admin_token('test-token')))
    assert client.put('/api/v1/config/fetch-priorities', json={'priorities': {}}).status_code == 401
    assert client.get('/api/v1/config/fetch-priorities').status_code == 401
    assert client.get('/api/v1/config/fetch-priorities', headers={'X-Admin-Token': 'test-token'}).status_code == 200


def test_x_preview_uses_saved_order(priority_client, monkeypatch):
    from app.routers import articles
    from app.services.fetchers import x_providers
    client = priority_client
    client.app.include_router(articles.router, prefix='/api/v1/articles')
    client.put('/api/v1/config/fetch-priorities', json={'priorities': {'x': ['x_graphql', 'tikhub', 'twitter_cli']}})
    async def download(url, *args):
        return {'payload': {'tweet_text': '按后台顺序获取的正文', 'media_items': []}}
    def paid(*args):
        raise RuntimeError('此预览不应访问 TikHub')
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', download)
    monkeypatch.setattr(articles, 'fetch_tikhub_tweet', paid)
    response = client.get('/api/v1/articles/x-preview', params={'url': 'https://x.com/author/status/123456789'})
    assert response.status_code == 200
    assert response.json()['tweet_text'] == '按后台顺序获取的正文'


def test_wechat_priority_can_be_saved_independently_of_x(priority_client):
    client = priority_client
    client.put('/api/v1/config/fetch-priorities', json={'priorities': {'x': ['x_graphql', 'tikhub', 'twitter_cli']}})
    response = client.put('/api/v1/config/fetch-priorities', json={'priorities': {'wechat': ['content_downloader', 'tikhub']}})
    assert response.status_code == 200
    stored = client.get('/api/v1/config/fetch-priorities').json()['priorities']
    assert stored['wechat'] == ['content_downloader', 'tikhub']
    assert stored['x'] == ['x_graphql', 'tikhub', 'twitter_cli']


def test_existing_saved_x_order_appends_new_cli_provider(priority_client):
    asyncio.run(settings_store.save_settings({'fetchProviderPriorities': json.dumps({'x': ['x_graphql', 'tikhub']})}))
    current = priority_client.get('/api/v1/config/fetch-priorities').json()['priorities']['x']
    assert current == ['x_graphql', 'tikhub', 'twitter_cli']


def test_cli_can_be_saved_as_x_first_choice(priority_client):
    response = priority_client.put('/api/v1/config/fetch-priorities', json={
        'priorities': {'x': ['twitter_cli', 'tikhub', 'x_graphql']},
    })
    assert response.status_code == 200
    saved = priority_client.get('/api/v1/config/fetch-priorities').json()
    assert saved['priorities']['x'] == ['twitter_cli', 'tikhub', 'x_graphql']
    assert saved['priorities']['wechat'] == ['tikhub', 'content_downloader']
    assert 'status' in saved['providers']['twitter_cli']
