import asyncio
import json

import pytest

from app.services import knowledge_qa as qa
from app.services.knowledge_retrieval import RetrievedChunk


CHUNKS = [RetrievedChunk(1, 'one', '资料一', 'other', 'SQLite 使用事务。', 'v1'), RetrievedChunk(2, 'two', '资料二', 'other', 'Redis 内存缓存。', 'v2')]


def test_no_chunks_returns_insufficient_without_call(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('No model request without evidence')
    monkeypatch.setattr(qa, 'chat_completion', forbidden)
    answer = asyncio.run(qa.generate_knowledge_answer('missing', [], [], {}))
    assert answer.insufficient_evidence and not answer.sources


def test_valid_citations_use_server_snapshots():
    answer = qa.parse_answer(json.dumps({'answer': '内存缓存[2]', 'insufficient_evidence': False, 'sources': [{'excerpt': '模型伪造'}]}), CHUNKS)
    assert answer.sources == [dict(number=2, article_id='two', title='资料二', source_type='other', excerpt='Redis 内存缓存。', article_updated_at='v2', article_exists=True)]


@pytest.mark.parametrize('raw', ['broken', '', '{"answer":"无引用","insufficient_evidence":false}', '{"answer":"错误[999]","insufficient_evidence":false}', '{"answer":"x","insufficient_evidence":"false"}'])
def test_rejects_missing_unknown_or_malformed_citations(raw):
    with pytest.raises(qa.KnowledgeAnswerError):
        qa.parse_answer(raw, CHUNKS)


def test_history_and_context_budgets():
    history = [dict(question=f'问题{i}' + 'x' * 2000, answer='a' * 2000) for i in range(12)]
    messages = qa.build_messages('当前问题', CHUNKS, history)
    past = [m for m in messages if m['role'] in ('assistant', 'user')][:-1]
    assert len(past) <= 12
    assert sum(len(m['content']) for m in past) <= 8000
    assert '问题0' not in ''.join(m['content'] for m in past)


def test_model_request_uses_bounded_generation(monkeypatch):
    async def model(messages, config, **kwargs):
        assert kwargs['temperature'] == 0.2 and kwargs['max_tokens'] == 300
        assert 'SQLite 使用事务。' in messages[-1]['content']
        return '{"answer":"使用事务[1]","insufficient_evidence":false}'
    monkeypatch.setattr(qa, 'chat_completion', model)
    result = asyncio.run(qa.generate_knowledge_answer('SQLite?', CHUNKS, [], {'llmMaxTokens': '300'}))
    assert result.sources[0]['article_id'] == 'one'
