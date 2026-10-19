import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowUp, BookOpenText, ChevronDown, History, Loader2, MessageSquare, Plus, RefreshCw, Trash2 } from 'lucide-react';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { formatAbsolute } from '../../../utils/formatDate';
import { knowledgeClient, KnowledgeRequestError } from '../client';
import { useKnowledgeStore } from '../knowledgeStore';
import KnowledgeAnswer from '../components/KnowledgeAnswer';
import type { KnowledgeStatus } from '../types';
import '../knowledge.css';

export default function AdminKnowledge() {
  const [params, setParams] = useSearchParams();
  const id = params.get('conversation') || '';
  const state = useKnowledgeStore();
  const detail = state.byId[id];
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [error, setError] = useState('');
  const [drafts, setDrafts] = useState<Record<string,string>>({});
  const [creating, setCreating] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteId, setDeleteId] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [authExpired, setAuthExpired] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const turnsRef = useRef<HTMLDivElement>(null);
  const pending = Boolean(state.pendingById[id] || detail?.turns.some(turn => turn.status === 'pending'));
  const draft = drafts[id] || '';
  const available = status?.model_configured && status?.index_available && !authExpired;

  const reportError = (reason: unknown) => {
    setError(reason instanceof Error ? reason.message : '加载失败，请稍后重试。');
    if (reason instanceof KnowledgeRequestError && reason.status === 401) setAuthExpired(true);
  };

  useEffect(() => {
    let active = true;
    setError('');
    Promise.all([knowledgeClient.status(), state.loadList(true)]).then(([result]) => {
      if (!active) return;
      setStatus(result); setAuthExpired(false);
    }).catch(reason => {if (active) reportError(reason);});
    return () => {active = false;};
  }, [reload]);

  useEffect(() => {
    setHistoryOpen(false); setError('');
    if (!id) {setLoading(false); return;}
    let active = true;
    setLoading(true);
    state.loadConversation(id).catch(reason => {if (active) reportError(reason);})
      .finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [id, reload]);

  // Recover an in-flight request after reload; the backend owns the saved turn.
  useEffect(() => {
    if (!id || !detail?.turns.some(turn => turn.status === 'pending') || state.pendingById[id]) return;
    const timer = window.setInterval(() => state.loadConversation(id).catch(reportError), 2000);
    return () => window.clearInterval(timer);
  }, [id, detail?.turns, state.pendingById[id]]);

  useEffect(() => {
    turnsRef.current?.scrollTo({top:turnsRef.current.scrollHeight, behavior:'instant'});
  }, [id, detail?.turns.length, pending]);

  async function create() {
    setCreating(true); setError('');
    try {
      const nextId = await state.createConversation();
      setParams({conversation:nextId});
      inputRef.current?.focus();
      return nextId;
    } catch (reason) { reportError(reason); return ''; }
    finally { setCreating(false); }
  }

  async function submit(event?: FormEvent, questionOverride?: string) {
    event?.preventDefault();
    const question = (questionOverride || draft).trim();
    if (!question || pending || creating || !available || question.length > 2000) return;
    setError('');
    const targetId = id || await create();
    if (!targetId) return;
    setDrafts(current => ({...current,[id]:'',[targetId]:''}));
    try {
      await state.sendQuestion(targetId, question);
      knowledgeClient.status().then(setStatus).catch(() => {});
    } catch (reason) {
      setDrafts(current => ({...current,[targetId]:question}));
      // Errors are stored per conversation; don't replace another conversation's status.
      if (reason instanceof KnowledgeRequestError && reason.status === 401) setAuthExpired(true);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await state.deleteConversation(deleteId);
      if (id === deleteId) setParams({});
      setDeleteId('');
    } catch (reason) {reportError(reason);}
    finally {setDeleting(false);}
  }

  return <section className="knowledge-page" aria-label="知识库问答工作区">
    <div className="knowledge-overview"><span><BookOpenText size={15}/>根据已保存文章回答，并提供原文引用</span>
      <span className="knowledge-library-count">{status ? `${status.article_count} 篇文章` : '正在连接文章库'}</span></div>
    {error && <div className="knowledge-notice" role="alert"><span>{error}</span><button onClick={() => setReload(v => v + 1)}><RefreshCw size={13}/>重试</button>{authExpired && <Link to="/admin">重新登录</Link>}</div>}
    {status?.message && <div className="knowledge-notice"><span>{status.message}</span><Link to="/admin/model">配置模型服务</Link></div>}
    <div className="knowledge-workspace">
      <aside className={`knowledge-history${historyOpen ? ' is-open' : ''}`} aria-label="历史会话">
        <div className="knowledge-history-head"><button className="knowledge-history-toggle" aria-expanded={historyOpen} onClick={() => setHistoryOpen(v => !v)}><History size={15}/><span>历史会话</span><ChevronDown size={14}/></button>
          <button className="knowledge-new" onClick={() => void create()} disabled={creating} aria-label="新建会话">{creating ? <Loader2 size={15} className="animate-spin"/> : <Plus size={15}/>}<span>新建</span></button></div>
        <div className="knowledge-history-body">
          {state.conversations.length === 0 && <p className="knowledge-history-empty">提问后，会话会保存在这里。</p>}
          <div className="knowledge-conversations">{state.conversations.map(conversation => <div className={`knowledge-conversation${id === conversation.id ? ' active' : ''}`} key={conversation.id}>
            <button className="knowledge-conversation-select" aria-current={id === conversation.id ? 'page' : undefined} onClick={() => setParams({conversation:conversation.id})} title={conversation.title}>
              {state.pendingById[conversation.id] ? <Loader2 size={14} className="animate-spin"/> : <MessageSquare size={14}/>}<span className="knowledge-conversation-label"><span>{conversation.title}</span><small>{formatAbsolute(new Date(conversation.updated_at))}</small></span>
            </button>
            <button className="knowledge-delete" aria-label={`删除会话：${conversation.title}`} disabled={Boolean(state.pendingById[conversation.id])} onClick={() => setDeleteId(conversation.id)}><Trash2 size={13}/></button>
          </div>)}</div>
          {state.conversations.length < state.total && <button className="knowledge-more" onClick={() => state.loadList(false).catch(reportError)}>加载更多会话</button>}
        </div>
      </aside>
      <div className="knowledge-chat">
        <div className="knowledge-chat-heading"><span>{detail?.conversation.title || '新会话'}</span><span>{pending ? '正在回答' : '知识库问答'}</span></div>
        <div className="knowledge-messages" ref={turnsRef} aria-label="对话记录" aria-busy={pending}>
          {loading && !detail ? <div className="knowledge-loading"><Loader2 size={20} className="animate-spin"/>加载会话…</div> : !detail?.turns.length ? <div className="knowledge-empty">
            <div className="knowledge-empty-symbol"><BookOpenText size={30} strokeWidth={1.3}/></div>
            <h2>向你的文章库提问</h2><p>{status?.article_count === 0 ? '先导入一些文章，再从这里查找和理解其中的内容。' : '查找观点、理解概念，或对照多篇文章。回答中的编号可以展开核对原文。'}</p>
            <div className="knowledge-suggestions"><button onClick={() => {setDrafts(v => ({...v,[id]:'我保存的文章中，KV Cache 如何减少重复计算？'}));inputRef.current?.focus();}}>查找一个技术概念 <span>↗</span></button><button onClick={() => {setDrafts(v => ({...v,[id]:'对比文章中 SQLite 和 Redis 的适用场景。'}));inputRef.current?.focus();}}>对比不同技术方案 <span>↗</span></button></div>
            {status?.article_count === 0 && <Link to="/">去导入文章</Link>}
          </div> : detail.turns.map(turn => <article key={turn.id} className="knowledge-turn">
            <div className="knowledge-question"><span className="knowledge-speaker">你</span><p>{turn.question}</p></div>
            <div className="knowledge-response"><span className="knowledge-speaker"><BookOpenText size={13}/>SynthAI</span>
              {turn.status === 'pending' ? <p className="knowledge-pending" role="status"><Loader2 size={15} className="animate-spin"/>正在查找资料并生成回答…</p> : turn.status === 'completed' ? <KnowledgeAnswer turn={turn}/> : <div className="knowledge-turn-error"><p>{turn.error_message || '回答已中断，请重新提问。'}</p><button onClick={() => void submit(undefined,turn.question)} disabled={pending || !available}><RefreshCw size={13}/>重新提问</button></div>}
            </div>
          </article>)}
        </div>
        <div className="knowledge-composer-wrap">
          {state.errorsById[id] && <div className="knowledge-send-error" role="alert">{state.errorsById[id]}</div>}
          <form className="knowledge-composer" onSubmit={event => void submit(event)}>
            <textarea ref={inputRef} aria-label="向知识库提问" placeholder={available ? '输入问题，查找文章中的答案…' : '配置模型服务后即可提问'} value={draft} maxLength={2000} rows={2} onChange={event => setDrafts(v => ({...v,[id]:event.target.value}))}
              onKeyDown={event => {if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {event.preventDefault();void submit();}}}/>
            <div className="knowledge-composer-bottom"><span>{pending ? '回答完成后可继续追问' : 'Enter 发送 · Shift + Enter 换行'}</span><div><small>{draft.length > 1600 ? `${draft.length}/2000` : ''}</small><button type="submit" aria-label="发送问题" disabled={!draft.trim() || pending || creating || !available}>{pending ? <Loader2 size={17} className="animate-spin"/> : <ArrowUp size={18}/>}</button></div></div>
          </form>
          <p className="knowledge-composer-note">根据检索到的文章片段生成，请结合原文核对。</p>
        </div>
      </div>
    </div>
    <ConfirmDialog open={Boolean(deleteId)} title="删除这段会话？" description="问题、回答和引用记录将一并删除。" busy={deleting} onCancel={() => setDeleteId('')} onConfirm={() => void confirmDelete()}/>
  </section>;
}
