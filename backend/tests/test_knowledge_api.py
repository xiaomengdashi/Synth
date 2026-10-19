import asyncio
import json
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.models import Article
from app.models.knowledge import KnowledgeTurn
from app.routers import knowledge
from app.services import settings_store, knowledge_qa
from app.services.knowledge_index import initialize_knowledge


AUTH = {'X-Admin-Token': 'qa-test-secret'}


@pytest.fixture
def qa_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'qa.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings_store, 'AsyncSessionLocal', sessions)
    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await initialize_knowledge(conn)
        await settings_store.set_admin_token_hash(settings_store.hash_admin_token('qa-test-secret'))
        async with sessions() as db:
            db.add(Article(id='source', title='技术资料', content_md='Redis 将数据缓存在内存中。', original_url='', source_type='other'))
            await db.commit()
    asyncio.run(prepare())
    async def database():
        async with sessions() as db:
            yield db
    async def config():
        return dict(baseUrl='https://example.invalid', apiKey='SENSITIVE-KEY', modelName='qa-test')
    async def model(*args, **kwargs):
        return '{"answer":"Redis 使用内存缓存[1]","insufficient_evidence":false}'
    monkeypatch.setattr(knowledge, 'load_settings', config)
    monkeypatch.setattr(knowledge_qa, 'chat_completion', model)
    app = FastAPI()
    app.include_router(knowledge.router, prefix='/api/v1/knowledge')
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    asyncio.run(engine.dispose())


def new_conversation(client):
    response = client.post('/api/v1/knowledge/conversations', headers=AUTH)
    assert response.status_code == 201
    return response.json()['id']


def send(client, cid, request='request', question='Redis'):
    return client.post(f'/api/v1/knowledge/conversations/{cid}/messages', headers=AUTH, json=dict(question=question, request_id=request))


def test_knowledge_requires_initialized_admin_on_every_endpoint(qa_client, monkeypatch):
    client, _ = qa_client
    paths = [('get', '/status'), ('get', '/conversations'), ('post', '/conversations'), ('get', '/conversations/x'), ('delete', '/conversations/x'), ('post', '/conversations/x/messages')]
    for method, path in paths:
        assert getattr(client, method)('/api/v1/knowledge' + path).status_code == 401
    async def empty(): return ''
    monkeypatch.setattr(knowledge, 'get_admin_token_hash', empty)
    assert client.get('/api/v1/knowledge/status', headers=AUTH).status_code == 503


def test_conversations_survive_reload_and_delete_explicitly(qa_client):
    client, sessions = qa_client
    cid = new_conversation(client)
    result = send(client, cid).json()
    assert result['status'] == 'completed' and result['sources'][0]['excerpt'].startswith('Redis')
    assert client.get('/api/v1/knowledge/conversations', headers=AUTH).json()['total'] == 1
    saved = client.get(f'/api/v1/knowledge/conversations/{cid}', headers=AUTH).json()
    assert saved['turns'][0]['answer'] == result['answer']
    assert client.delete(f'/api/v1/knowledge/conversations/{cid}', headers=AUTH).status_code == 204
    async def remaining():
        async with sessions() as db:
            return (await db.scalars(select(KnowledgeTurn))).all()
    assert asyncio.run(remaining()) == []


def test_same_request_generates_once(qa_client, monkeypatch):
    client, _ = qa_client
    cid = new_conversation(client)
    first = send(client, cid)
    async def forbidden(*args, **kwargs): raise AssertionError('Repeated request generated again')
    monkeypatch.setattr(knowledge_qa, 'chat_completion', forbidden)
    assert send(client, cid).json()['id'] == first.json()['id']


def test_model_errors_are_sanitized_and_pending_recovers(qa_client, monkeypatch):
    client, _ = qa_client
    async def broken(*args, **kwargs): raise RuntimeError('SENSITIVE-KEY <script>secret</script>')
    monkeypatch.setattr(knowledge_qa, 'chat_completion', broken)
    cid = new_conversation(client)
    response = send(client, cid)
    assert response.status_code == 502 and 'SENSITIVE' not in response.text
    saved = client.get(f'/api/v1/knowledge/conversations/{cid}', headers=AUTH).json()
    assert saved['turns'][0]['status'] == 'failed' and 'SENSITIVE' not in json.dumps(saved)
    assert send(client, cid).json()['status'] == 'failed'


def test_unknown_conversation_and_question_validation(qa_client):
    client, _ = qa_client
    assert send(client, 'missing').status_code == 404
    cid = new_conversation(client)
    assert send(client, cid, question='   ').status_code == 422
    assert send(client, cid, question='x' * 2001).status_code == 422
    response = send(client, cid, question='没有匹配的火星栽培资料')
    assert response.json()['insufficient_evidence']


def test_status_exposes_counts_without_credentials(qa_client):
    client, _ = qa_client
    status = client.get('/api/v1/knowledge/status', headers=AUTH)
    assert status.json()['article_count'] == 1 and status.json()['model_configured']
    assert 'SENSITIVE' not in status.text and 'apiKey' not in status.text


def test_busy_conversation_rejects_send_and_delete(qa_client, monkeypatch):
    client, _ = qa_client
    entered, release = threading.Event(), threading.Event()
    async def delayed(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return '{"answer":"内存[1]","insufficient_evidence":false}'
    monkeypatch.setattr(knowledge_qa, 'chat_completion', delayed)
    cid = new_conversation(client)
    results = []
    worker = threading.Thread(target=lambda: results.append(send(client, cid)))
    worker.start()
    try:
        assert entered.wait(3)
        assert send(client, cid, 'other').status_code == 409
        assert client.delete(f'/api/v1/knowledge/conversations/{cid}', headers=AUTH).status_code == 409
    finally:
        release.set()
        worker.join(5)
    assert results[0].status_code == 200


def test_deleted_during_generation_keeps_source_snapshot(qa_client, monkeypatch):
    client, sessions = qa_client
    async def model(*args, **kwargs):
        async with sessions() as db:
            await db.execute(delete(Article).where(Article.id == 'source'))
            await db.commit()
        return '{"answer":"内存[1]","insufficient_evidence":false}'
    monkeypatch.setattr(knowledge_qa, 'chat_completion', model)
    cid = new_conversation(client)
    result = send(client, cid).json()
    assert result['sources'][0]['article_exists'] is False
    assert 'Redis' in result['sources'][0]['excerpt']
    assert send(client, cid, 'next').json()['insufficient_evidence']


def test_same_request_is_rechecked_after_waiting_for_configuration(qa_client, monkeypatch):
    client, _ = qa_client
    first_entered, second_entered, first_complete = threading.Event(), threading.Event(), threading.Event()
    calls = 0
    async def delayed_config():
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            await asyncio.to_thread(second_entered.wait, 5)
        else:
            second_entered.set()
            await asyncio.to_thread(first_complete.wait, 5)
        return dict(baseUrl='https://example.invalid',apiKey='test',modelName='test')
    monkeypatch.setattr(knowledge,'load_settings',delayed_config)
    cid = new_conversation(client)
    results = []
    def first():
        try: results.append(send(client,cid,'same-id'))
        finally: first_complete.set()
    a = threading.Thread(target=first)
    b = threading.Thread(target=lambda: results.append(send(client,cid,'same-id')))
    a.start()
    assert first_entered.wait(3)
    b.start()
    a.join(8); b.join(8)
    assert len(results) == 2
    assert [r.status_code for r in results] == [200,200]
    assert results[0].json()['id'] == results[1].json()['id']
