"""Regression coverage for the real settings, account and query HTTP boundaries."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.routers import config, tikhub
from app.services import settings_store
from app.services.fetchers import tikhub as upstream


USER_INFO = {
    'code': 200,
    'api_key_data': {'api_key_name': 'SynthAI', 'api_key_status': 1,
                     'api_key_scopes': ['/api/v1/twitter/', '/api/v1/bilibili/'],
                     'created_at': '2026-09-01T00:00:00', 'expires_at': None},
    'user_data': {'email': 'test@example.com', 'balance': '4.966', 'free_credit': '0',
                  'is_active': True, 'email_verified': True, 'account_disabled': False},
}


@pytest.fixture
def console(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'settings.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    monkeypatch.setattr(settings_store, 'AsyncSessionLocal', sessions)
    app = FastAPI()
    app.include_router(config.router, prefix='/api/v1/config')
    app.include_router(tikhub.router, prefix='/api/v1/tikhub')

    def write_settings(values):
        asyncio.run(settings_store.save_settings(values))

    def stored() -> dict:
        return asyncio.run(settings_store.load_settings())

    with TestClient(app) as client:
        yield client, write_settings, stored
    asyncio.run(engine.dispose())


def test_public_config_masks_key_and_legacy_save_cannot_overwrite_it(console):
    client, write_settings, stored = console
    write_settings({'apiKey': 'model-private-key', 'tikhubApiKey': 'real-private-token'})
    response = client.get('/api/v1/config')
    assert 'real-private-token' not in response.text
    assert 'model-private-key' not in response.text
    assert response.json()['apiKey'] == '••••-key'
    assert response.json()['tikhubConfigured'] is True
    for legacy in ['configured', '', 'stale-browser-token']:
        response = client.post('/api/v1/config', json={
            'apiKey': '••••-key', 'baseUrl': 'https://example.com', 'modelName': 'model',
            'tikhubApiKey': legacy,
        })
        assert response.status_code == 200
        assert stored()['tikhubApiKey'] == 'real-private-token'
    assert stored()['apiKey'] == 'model-private-key'


def test_key_metadata_and_removal(console):
    client, write_settings, stored = console
    write_settings({'tikhubApiKey': 'stored-secret', 'apiKey': 'llm'})
    response = client.get('/api/v1/tikhub/key')
    assert response.status_code == 200
    assert response.json()['source'] == 'config'
    assert 'stored-secret' not in response.text
    response = client.delete('/api/v1/tikhub/key')
    assert response.status_code == 200
    assert response.json()['source'] is None
    assert response.json()['configured'] is False
    assert stored()['apiKey'] == 'llm'
    assert not stored()['tikhubApiKey']
    assert client.get('/api/v1/config').json()['tikhubConfigured'] is False


def test_verification_rejects_disabled_account_without_overwriting(console, monkeypatch):
    client, write_settings, stored = console
    write_settings({'tikhubApiKey': 'keep-me'})
    info = {**USER_INFO, 'user_data': {**USER_INFO['user_data'], 'is_active': False}}
    monkeypatch.setattr(upstream.httpx, 'request', lambda *a, **kw: httpx.Response(200, json=info))
    response = client.post('/api/v1/tikhub/key', json={'apiKey': 'disabled'})
    assert response.status_code == 400
    assert stored()['tikhubApiKey'] == 'keep-me'


def test_account_normalizes_numbers_and_reports_partial_usage_failure(console, monkeypatch):
    client, write_settings, _ = console
    write_settings({'tikhubApiKey': 'saved-key'})

    def request(method, url, **kw):
        assert kw['headers']['Authorization'] == 'Bearer saved-key'
        if url.endswith('get_user_info'):
            return httpx.Response(200, json=USER_INFO)
        return httpx.Response(503, json={'detail': 'temporarily unavailable'})

    monkeypatch.setattr(upstream.httpx, 'request', request)
    response = client.get('/api/v1/tikhub/account')
    assert response.status_code == 200
    data = response.json()
    assert data['user']['balance'] == 4.966
    assert data['api_key']['scopes'] == ['/api/v1/twitter/', '/api/v1/bilibili/']
    assert data['daily_usage'] is None
    assert data['warnings']


def test_query_catalog_supports_platform_and_search_without_a_key(console):
    client, _, _ = console
    response = client.get('/api/v1/tikhub/catalog', params={'platform': 'twitter', 'q': 'fetch_tweet_detail'})
    assert response.status_code == 200
    data = response.json()
    assert all(p['id'] != 'douyin' for p in data['platforms'])
    endpoint = next(item for item in data['items'] if item['path'] == '/api/v1/twitter/web/fetch_tweet_detail')
    assert endpoint['method'] == 'GET'
    assert endpoint['parameters'][0]['name'] == 'tweet_id'
    assert endpoint['parameters'][0]['required'] is True


def test_query_catalog_keeps_arbitrary_object_request_body(console):
    client, _, _ = console
    response = client.get('/api/v1/tikhub/catalog', params={
        'platform': 'zhihu', 'q': 'fetch_scholar_search_v3',
    })
    assert response.status_code == 200
    endpoint = next(item for item in response.json()['items'] if item['path'].endswith('fetch_scholar_search_v3'))
    body = next(parameter for parameter in endpoint['parameters'] if parameter['name'] == '$body')
    assert body['in'] == 'body_root'
    assert body['schema']['type'] == 'object'


def test_query_uses_saved_key_and_preserves_large_ids(console, monkeypatch):
    client, write_settings, _ = console
    write_settings({'tikhubApiKey': 'private-token'})

    def request(method, url, **kw):
        assert method == 'GET'
        assert url == 'https://api.tikhub.io/api/v1/twitter/web/fetch_tweet_detail'
        assert kw['headers']['Authorization'] == 'Bearer private-token'
        assert kw['params']['tweet_id'] == '1808168603721650364'
        return httpx.Response(200, json={'code': 200, 'data': {'id': 1808168603721650364, 'text': '正文'}})

    monkeypatch.setattr(upstream.httpx, 'request', request)
    response = client.post('/api/v1/tikhub/query', json={
        'endpoint_id': 'GET /api/v1/twitter/web/fetch_tweet_detail',
        'parameters': {'tweet_id': '1808168603721650364'},
    })
    assert response.status_code == 200
    assert response.json()['data']['data']['id'] == '1808168603721650364'
    assert 'private-token' not in response.text


@pytest.mark.parametrize('endpoint,parameters', [
    ('GET https://evil.example', {}),
    ('GET /api/v1/tiktok/app/v3/register_device', {}),
    ('GET /api/v1/twitter/web/fetch_tweet_detail', {}),
    ('GET /api/v1/twitter/web/fetch_tweet_detail', {'tweet_id': '1', 'Authorization': 'override'}),
    ('GET /api/v1/douyin/web/fetch_one_video', {'aweme_id': '1', 'need_anchor_info': 'not-a-bool'}),
])
def test_invalid_query_never_reaches_upstream(console, monkeypatch, endpoint, parameters):
    client, write_settings, _ = console
    write_settings({'tikhubApiKey': 'saved-key'})

    def unexpected(*a, **kw):
        pytest.fail('Invalid query was forwarded to TikHub')

    monkeypatch.setattr(upstream.httpx, 'request', unexpected)
    response = client.post('/api/v1/tikhub/query', json={'endpoint_id': endpoint, 'parameters': parameters})
    assert response.status_code in (400, 422)


def test_post_query_sends_json_body(console, monkeypatch):
    client, write_settings, _ = console
    write_settings({'tikhubApiKey': 'saved-key'})

    def request(method, url, **kw):
        assert method == 'POST'
        assert url.endswith('/wechat_mp/v2/fetch_article_detail_h5')
        assert kw['json']['url'] == 'https://mp.weixin.qq.com/s/test'
        assert kw['json']['raw'] is False
        return httpx.Response(200, json={'code': 200, 'data': {'content': {'title': '文章'}}})

    monkeypatch.setattr(upstream.httpx, 'request', request)
    response = client.post('/api/v1/tikhub/query', json={
        'endpoint_id': 'POST /api/v1/wechat_mp/v2/fetch_article_detail_h5',
        'parameters': {'url': 'https://mp.weixin.qq.com/s/test', 'raw': False},
    })
    assert response.status_code == 200
    assert response.json()['data']['data']['content']['title'] == '文章'


def test_missing_key_and_upstream_failure_are_distinct(console, monkeypatch):
    client, write_settings, _ = console
    payload = {'endpoint_id': 'GET /api/v1/twitter/web/fetch_tweet_detail', 'parameters': {'tweet_id': '1'}}
    response = client.post('/api/v1/tikhub/query', json=payload)
    assert response.status_code == 400
    write_settings({'tikhubApiKey': 'saved-key'})
    monkeypatch.setattr(upstream.httpx, 'request', lambda *a, **kw: httpx.Response(429, json={}))
    response = client.post('/api/v1/tikhub/query', json=payload)
    assert response.status_code == 429


@pytest.mark.parametrize('payload', [[], None, {'detail': 'Unauthorized'}, {'code': 401, 'message': 'secret-token rejected'}])
def test_malformed_upstream_payload_is_safe(payload, monkeypatch):
    monkeypatch.setattr(upstream.httpx, 'request', lambda *a, **kw: httpx.Response(200, json=payload))
    with pytest.raises(upstream.TikHubError) as error:
        upstream.verify_tikhub_token('secret-token')
    assert 'secret-token' not in str(error.value)


def test_x_preview_uses_saved_key(console, monkeypatch):
    from app.database import get_db
    from app.routers import articles
    from app.services.runtime_store import ARTICLES_DB
    _, write_settings, _ = console
    write_settings({'tikhubApiKey': 'saved-preview-key'})
    seen = []

    def fetch(url, runtime_config):
        seen.append(runtime_config)
        return {'payload': {'title': '预览', 'tweet_text': '可保存的预览正文', 'media_items': []}}

    monkeypatch.setattr(articles, 'fetch_tikhub_tweet', fetch)
    app = FastAPI()
    app.include_router(articles.router, prefix='/articles')

    class _EmptyDb:
        async def get(self, model, pk):
            return None

    async def empty_db():
        yield _EmptyDb()

    app.dependency_overrides[get_db] = empty_db
    ARTICLES_DB['console-x-preview'] = {'id': 'console-x-preview', 'original_url': 'https://x.com/a/status/123'}
    try:
        with TestClient(app) as http:
            response = http.get('/articles/console-x-preview/x-preview')
    finally:
        ARTICLES_DB.pop('console-x-preview', None)
        articles._x_preview_cache.pop('console-x-preview', None)
    assert response.status_code == 200
    assert seen[0]['tikhubApiKey'] == 'saved-preview-key'


def test_task_submit_uses_server_key_instead_of_browser_placeholder(console, monkeypatch):
    from app.routers import tasks
    _, write_settings, _ = console
    write_settings({'tikhubApiKey': 'server-token'})
    captured = []

    async def create(*args):
        pass

    async def process(task_id, url, runtime_config):
        captured.append(runtime_config['tikhubApiKey'])

    monkeypatch.setattr(tasks, 'create_task_record', create)
    monkeypatch.setattr(tasks, 'process_task', process)
    monkeypatch.setattr(tasks, 'TASKS_DB', {})
    app = FastAPI()
    app.include_router(tasks.router, prefix='/tasks')
    with TestClient(app) as http:
        response = http.post('/tasks/submit', json={'url': 'https://x.com/a/status/123', 'config': {'tikhubApiKey': 'configured'}})
    assert response.status_code == 200
    assert captured == ['server-token']


@pytest.mark.parametrize('parameters,expected', [({}, None), ({'$body': 'session=example'}, 'session=example')])
def test_optional_scalar_body_keeps_post_method(console, monkeypatch, parameters, expected):
    client, write_settings, _ = console
    write_settings({'tikhubApiKey': 'saved-key'})

    def request(method, url, **kw):
        assert method == 'POST'
        assert kw['json'] == expected
        return httpx.Response(200, json={'code': 200, 'data': ['filter']})

    monkeypatch.setattr(upstream.httpx, 'request', request)
    response = client.post('/api/v1/tikhub/query', json={
        'endpoint_id': 'POST /api/v1/tiktok/ads/get_top_ads_filters', 'parameters': parameters,
    })
    assert response.status_code == 200
    assert response.json()['data']['data'] == ['filter']


def test_array_body_and_redaction(console, monkeypatch):
    client, write_settings, _ = console
    write_settings({'tikhubApiKey': 'private-key'})

    def request(method, url, **kw):
        assert method == 'POST'
        assert kw['json'] == ['123', '456']
        return httpx.Response(200, json={'code': 200, 'data': {'api_key': 'private-key', 'text': 'private-key', 'cookie': 'session=secret', 'count': 2}})

    monkeypatch.setattr(upstream.httpx, 'request', request)
    response = client.post('/api/v1/tikhub/query', json={
        'endpoint_id': 'POST /api/v1/tiktok/app/v3/fetch_multi_video', 'parameters': {'$body': ['123', '456']},
    })
    assert response.status_code == 200
    assert 'private-key' not in response.text
    assert 'session=secret' not in response.text
    assert response.json()['data']['data']['count'] == 2
