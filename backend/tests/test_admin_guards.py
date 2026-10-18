"""未登录访客不得触达后台接口:配置/任务列表/模型测试/TikHub/HTML 导入的鉴权回归。

配套修复:models 接口曾允许把保存的明文 API Key 发往请求体指定的任意 baseUrl
(凭据外传),TikHub key 可被陌生人覆盖/删除,import-html 可匿名写库——
本文件逐一锁死这些入口,并保证快捷指令轮询等读者级接口保持开放。
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.routers import admin_auth, articles, config, models, tasks, tikhub
from app.services import settings_store

TOKEN = 'guard-secret-token'
AUTH = {'X-Admin-Token': TOKEN}


@pytest.fixture
def guard_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'guards.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    # 先切会话工厂再写数据,否则 set_admin_token_hash 会落到真实库
    monkeypatch.setattr(settings_store, 'AsyncSessionLocal', sessions)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await settings_store.set_admin_token_hash(settings_store.hash_admin_token(TOKEN))

    asyncio.run(prepare())

    async def database():
        async with sessions() as session:
            yield session

    app = FastAPI()
    app.include_router(config.router, prefix='/api/v1/config')
    app.include_router(tasks.router, prefix='/api/v1/tasks')
    app.include_router(models.router, prefix='/api/v1/models')
    app.include_router(tikhub.router, prefix='/api/v1/tikhub')
    app.include_router(articles.router, prefix='/api/v1/articles')
    app.include_router(admin_auth.router, prefix='/api/v1/admin-auth')
    app.dependency_overrides[get_db] = database
    app.state.sessions = sessions
    admin_auth._login_failures.clear()
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


@pytest.mark.parametrize('method,path,body', [
    ('get', '/api/v1/config', None),
    ('get', '/api/v1/tasks', None),
    ('post', '/api/v1/models/list', {'baseUrl': 'https://attacker.example'}),
    ('post', '/api/v1/models/test', {'baseUrl': 'https://attacker.example', 'apiKey': ''}),
    ('get', '/api/v1/tikhub/key', None),
    ('post', '/api/v1/tikhub/key', {'apiKey': 'attacker-token'}),
    ('delete', '/api/v1/tikhub/key', None),
    ('get', '/api/v1/tikhub/account', None),
    ('get', '/api/v1/tikhub/catalog', None),
    ('post', '/api/v1/tikhub/query', {'endpoint_id': 'x', 'parameters': {}}),
    ('post', '/api/v1/articles/import-html', {'original_url': 'https://x.example', 'html': '<p>x</p>'}),
])
def test_admin_endpoints_reject_missing_token(guard_client, method, path, body):
    if body is None:
        response = getattr(guard_client, method)(path)
    else:
        response = getattr(guard_client, method)(path, json=body)
    assert response.status_code == 401, f'{method.upper()} {path} 应拒绝未登录访问'


def test_admin_endpoints_accept_valid_token(guard_client):
    assert guard_client.get('/api/v1/config', headers=AUTH).status_code == 200
    assert guard_client.get('/api/v1/tasks', headers=AUTH).status_code == 200


def test_task_status_polling_stays_public(guard_client):
    # iPhone 快捷指令轮询入口保持开放:鉴权层放行(业务层对未知 id 返回 200 兜底体)
    response = guard_client.get('/api/v1/tasks/unknown-id/status')
    assert response.status_code == 200 and 'error' in response.json()


def test_article_reader_endpoints_hide_internal_fields(guard_client):
    # 读者级详情/列表/导出只出文章内容与展示元信息:
    # email_message_id 是内部去重键,account_name 里的发件人邮箱须脱敏
    import datetime

    from app.models import Article as ArticleModel
    sessions = guard_client.app.state.sessions

    async def seed():
        async with sessions() as session:
            session.add(ArticleModel(
                id='audit-1', title='审计样例', summary='摘要', content_md='正文',
                original_url='https://x.com/a/status/1', source_type='x',
                account_name='friend@163.com',
                email_message_id='<secret-message-id@mailer.example>',
                created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
            ))
            await session.commit()

    asyncio.run(seed())
    detail = guard_client.get('/api/v1/articles/audit-1').json()
    assert 'email_message_id' not in detail
    assert detail['account_name'] == '邮件来稿'
    listing = guard_client.get('/api/v1/articles?limit=5').json()['data'][0]
    assert 'email_message_id' not in listing
    assert listing['account_name'] == '邮件来稿'
    exported = guard_client.get('/api/v1/articles/audit-1/export').text
    assert 'friend@163.com' not in exported
    assert '邮件来稿' in exported


def test_x_preview_rejects_unknown_article(guard_client):
    # 旧形态(匿名自选任意推文 URL 的抓取代理)已下线:未入库的 id 一律 404
    assert guard_client.get('/api/v1/articles/not-stored/x-preview').status_code == 404


def test_login_rate_limit_locks_out_after_failures(guard_client, monkeypatch):
    for _ in range(admin_auth.LOGIN_RATE_LIMIT):
        assert guard_client.post('/api/v1/admin-auth/login', json={'token': 'wrong'}).status_code == 401
    assert guard_client.post('/api/v1/admin-auth/login', json={'token': 'wrong'}).status_code == 429
    # 锁定窗口内正确令牌同样被拒
    assert guard_client.post('/api/v1/admin-auth/login', json={'token': TOKEN}).status_code == 429
    # 窗口滑过后恢复,成功登录清零失败计数
    base = admin_auth._now()
    monkeypatch.setattr(admin_auth, '_now', lambda: base + admin_auth.LOGIN_RATE_WINDOW + 1)
    assert guard_client.post('/api/v1/admin-auth/login', json={'token': TOKEN}).status_code == 200
    assert guard_client.post('/api/v1/admin-auth/login', json={'token': 'wrong'}).status_code == 401


def test_api_docs_disabled():
    # 接口清单不对外暴露(docs/redoc/openapi 路由不注册;线上另有 nginx 只代理 /api)
    from main import app as main_app

    assert main_app.docs_url is None and main_app.openapi_url is None
    probe = TestClient(main_app)
    for path in ('/docs', '/redoc', '/openapi.json'):
        assert probe.get(path).status_code == 404
