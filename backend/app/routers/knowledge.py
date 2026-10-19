"""Authenticated, persistent knowledge conversations."""
import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Article
from app.models.knowledge import KnowledgeConversation, KnowledgeTurn, utc_now
from app.routers.admin_auth import require_admin
from app.services.settings_store import get_admin_token_hash, load_settings
from app.services.knowledge_index import get_index_status, sync_knowledge_index
from app.services.knowledge_retrieval import retrieve_chunks
from app.services.knowledge_qa import generate_knowledge_answer, KnowledgeAnswerError
from app.timezones import local_iso


async def require_knowledge_admin(x_admin_token: str = Header(default='')):
    if not await get_admin_token_hash():
        raise HTTPException(503, '请先设置后台访问令牌，再使用知识库问答。')
    await require_admin(x_admin_token)


router = APIRouter(dependencies=[Depends(require_knowledge_admin)])
_busy: set[str] = set()


class MessagePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=1, max_length=128)

    @field_validator('question', 'request_id', mode='before')
    @classmethod
    def strip_input(cls, value):
        return value.strip() if isinstance(value, str) else value


def conversation_payload(conversation):
    return dict(id=conversation.id, title=conversation.title, created_at=local_iso(conversation.created_at), updated_at=local_iso(conversation.updated_at))


async def turn_payload(db, turn):
    sources = json.loads(turn.sources_json or '[]')
    ids = [s['article_id'] for s in sources]
    existing = set((await db.scalars(select(Article.id).where(Article.id.in_(ids)))).all()) if ids else set()
    sources = [{**s, 'article_exists': s['article_id'] in existing} for s in sources]
    return dict(id=turn.id, conversation_id=turn.conversation_id, request_id=turn.request_id,
                question=turn.question, answer=turn.answer, status=turn.status,
                insufficient_evidence=turn.insufficient_evidence, sources=sources, error_message=turn.error_message,
                created_at=local_iso(turn.created_at), completed_at=local_iso(turn.completed_at))


async def get_conversation(db, cid):
    conversation = await db.get(KnowledgeConversation, cid)
    if not conversation:
        raise HTTPException(404, '会话不存在。')
    return conversation


@router.get('/status')
async def status(db: AsyncSession = Depends(get_db)):
    config = await load_settings()
    result = await get_index_status(db)
    result['model_configured'] = all(str(config.get(k) or '').strip() for k in ('baseUrl', 'apiKey', 'modelName'))
    result['message'] = '' if result['index_available'] else '当前服务器未启用 SQLite FTS5，知识库问答暂不可用。'
    if not result['model_configured']:
        result['message'] = '请先在模型服务中配置 Base URL、API Key 和模型名称。'
    return result


@router.get('/conversations')
async def list_conversations(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(KnowledgeConversation))
    rows = (await db.scalars(select(KnowledgeConversation).order_by(KnowledgeConversation.updated_at.desc(), KnowledgeConversation.id).limit(limit).offset(offset))).all()
    return dict(total=total, data=[conversation_payload(c) for c in rows])


@router.post('/conversations', status_code=201)
async def create_conversation(db: AsyncSession = Depends(get_db)):
    conversation = KnowledgeConversation(id=str(uuid4()))
    db.add(conversation)
    await db.commit()
    return conversation_payload(conversation)


@router.get('/conversations/{cid}')
async def conversation_detail(cid: str, db: AsyncSession = Depends(get_db)):
    conversation = await get_conversation(db, cid)
    turns = (await db.scalars(select(KnowledgeTurn).where(KnowledgeTurn.conversation_id == cid).order_by(KnowledgeTurn.created_at, KnowledgeTurn.id))).all()
    return dict(conversation=conversation_payload(conversation), turns=[await turn_payload(db, t) for t in turns])


@router.delete('/conversations/{cid}', status_code=204)
async def delete_conversation(cid: str, db: AsyncSession = Depends(get_db)):
    await get_conversation(db, cid)
    if cid in _busy:
        raise HTTPException(409, '会话正在生成回答，请稍后再删除。')
    _busy.add(cid)
    try:
        await db.execute(delete(KnowledgeTurn).where(KnowledgeTurn.conversation_id == cid))
        await db.execute(delete(KnowledgeConversation).where(KnowledgeConversation.id == cid))
        await db.commit()
    finally:
        _busy.discard(cid)
    return Response(status_code=204)


async def fail_turn(db, tid, cid, message, interrupted=False):
    await db.rollback()
    turn = await db.get(KnowledgeTurn, tid)
    if turn:
        turn.status = 'interrupted' if interrupted else 'failed'
        turn.error_message = message
        turn.completed_at = utc_now()
        conversation = await db.get(KnowledgeConversation, cid)
        if conversation:
            conversation.updated_at = utc_now()
        await db.commit()


@router.post('/conversations/{cid}/messages')
async def send_message(cid: str, payload: MessagePayload, db: AsyncSession = Depends(get_db)):
    conversation = await get_conversation(db, cid)
    existing = await db.scalar(select(KnowledgeTurn).where(KnowledgeTurn.conversation_id == cid, KnowledgeTurn.request_id == payload.request_id))
    if existing:
        if existing.status == 'pending':
            raise HTTPException(409, '这个问题正在处理中，请稍后查看。')
        return await turn_payload(db, existing)
    config = await load_settings()
    if not all(str(config.get(k) or '').strip() for k in ('baseUrl', 'apiKey', 'modelName')):
        raise HTTPException(503, '请先在模型服务中配置 Base URL、API Key 和模型名称。')
    if not (await get_index_status(db))['index_available']:
        raise HTTPException(503, '当前服务器未启用 SQLite FTS5，知识库问答暂不可用。')
    if cid in _busy:
        raise HTTPException(409, '会话正在生成回答，请等待完成后再提问。')
    _busy.add(cid)
    tid = str(uuid4())
    try:
        turn = KnowledgeTurn(id=tid, conversation_id=cid, request_id=payload.request_id, question=payload.question)
        db.add(turn)
        if conversation.title == '新会话':
            conversation.title = payload.question[:40]
        conversation.updated_at = utc_now()
        await db.commit()
        past = (await db.scalars(select(KnowledgeTurn).where(KnowledgeTurn.conversation_id == cid, KnowledgeTurn.status == 'completed').order_by(KnowledgeTurn.created_at.desc()).limit(6))).all()
        history = [dict(question=t.question, answer=t.answer) for t in reversed(past)]
        previous_ids = [s['article_id'] for s in json.loads(past[0].sources_json or '[]')] if past else []
        await db.commit()
        await sync_knowledge_index(db)
        chunks = await retrieve_chunks(db, payload.question, previous_questions=[h['question'] for h in history[-2:]], previous_article_ids=previous_ids)
        answer = await generate_knowledge_answer(payload.question, chunks, history, config)
        turn.answer = answer.answer
        turn.insufficient_evidence = answer.insufficient_evidence
        turn.sources_json = json.dumps(answer.sources, ensure_ascii=False)
        turn.status = 'completed'
        turn.completed_at = utc_now()
        conversation.updated_at = utc_now()
        await db.commit()
        return await turn_payload(db, turn)
    except asyncio.CancelledError:
        await asyncio.shield(fail_turn(db, tid, cid, '请求已中断，请重新提问。', interrupted=True))
        raise
    except TimeoutError:
        message = '模型回答超时，请稍后重试或调整模型服务超时设置。'
        await fail_turn(db, tid, cid, message)
        raise HTTPException(504, message) from None
    except KnowledgeAnswerError:
        message = '模型未返回有效的答案或资料引用，请检查模型服务后重试。'
        await fail_turn(db, tid, cid, message)
        raise HTTPException(502, message) from None
    except Exception:
        message = '知识库问答暂时失败，请稍后重试。'
        await fail_turn(db, tid, cid, message)
        raise HTTPException(502, message) from None
    finally:
        _busy.discard(cid)
