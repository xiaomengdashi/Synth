import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowUp, BookOpenText, ExternalLink, Headphones, History, Loader2, MessageCircle, Plus, RefreshCw, X } from 'lucide-react';
import type { AdminVerifyStatus } from '../../../hooks/useVerifiedAdminToken';
import { knowledgeClient, KnowledgeRequestError } from '../client';
import { useKnowledgeStore } from '../knowledgeStore';
import type { KnowledgeStatus } from '../types';
import '../knowledge.css';
import '../floatingKnowledge.css';

const KnowledgeAnswer = lazy(() => import('./KnowledgeAnswer'));
const SESSION_KEY = 'synthai-floating-knowledge-conversation';

function savedConversation() {
  try { return sessionStorage.getItem(SESSION_KEY) || ''; } catch { return ''; }
}

/** Mounted in the public layout so closing the panel or changing articles keeps the conversation. */
export default function FloatingKnowledgeChat({ adminStatus }: { adminStatus: AdminVerifyStatus }) {
  const state = useKnowledgeStore();
  const [open, setOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [panelHeight, setPanelHeight] = useState<number | null>(null);
  const [viewportHeight, setViewportHeight] = useState(window.innerHeight);
  const [resizing, setResizing] = useState(false);
  const [id, setId] = useState(savedConversation);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [reload, setReload] = useState(0);
  const launcher = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const historyControl = useRef<HTMLDivElement>(null);
  const historyButton = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const messages = useRef<HTMLDivElement>(null);
  const submitting = useRef(false);
  const panel = useRef<HTMLElement>(null);
  const resizeDrag = useRef<{ pointerId: number; y: number; height: number } | null>(null);
  const maxHeight = Math.max(0, viewportHeight - 12);
  const minHeight = Math.min(280, viewportHeight / 2, maxHeight);
  const currentHeight = panelHeight ?? viewportHeight / 2;
  const clampHeight = (height: number) => Math.round(Math.min(maxHeight, Math.max(minHeight, height)));
  const detail = state.byId[id];
  const draft = drafts[id] || '';
  const verified = adminStatus === 'verified';
  const pending = Boolean(state.pendingById[id] || detail?.turns.some(turn => turn.status === 'pending'));
  const available = verified && !expired && status?.model_configured && status?.index_available;

  const select = useCallback((nextId: string) => {
    setId(nextId);
    setHistoryOpen(false);
    setError('');
    try {
      if (nextId) sessionStorage.setItem(SESSION_KEY, nextId);
      else sessionStorage.removeItem(SESSION_KEY);
    } catch { /* Chat remains usable when browser storage is disabled. */ }
  }, []);

  const reportError = useCallback((reason: unknown) => {
    setError(reason instanceof Error ? reason.message : '连接失败，请稍后重试。');
    if (reason instanceof KnowledgeRequestError && reason.status === 401) setExpired(true);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setHistoryOpen(false);
    resizeDrag.current = null;
    setResizing(false);
    launcher.current?.focus();
  }, []);

  useEffect(() => {
    const resize = () => {
      const height = window.innerHeight;
      setViewportHeight(height);
      setPanelHeight(current => current === null ? null : Math.min(Math.max(0, height - 12), Math.max(Math.min(280, height / 2), current)));
      resizeDrag.current = null;
      setResizing(false);
    };
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  useEffect(() => {
    if (open) closeButton.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (historyOpen) { setHistoryOpen(false); historyButton.current?.focus(); }
      else close();
    };
    const outside = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node) || resizeDrag.current) return;
      if (!panel.current?.contains(target) && !launcher.current?.contains(target)) {
        close();
        return;
      }
      if (historyOpen && !historyControl.current?.contains(target)) setHistoryOpen(false);
    };
    const refresh = () => setReload(value => value + 1);
    document.addEventListener('keydown', escape);
    document.addEventListener('pointerdown', outside, true);
    window.addEventListener('focus', refresh);
    return () => {
      document.removeEventListener('keydown', escape);
      document.removeEventListener('pointerdown', outside, true);
      window.removeEventListener('focus', refresh);
    };
  }, [open, close, historyOpen]);

  useEffect(() => {
    if (!open || !verified) return;
    let active = true;
    setStatus(null);
    setError('');
    Promise.all([knowledgeClient.status(), state.loadList(true)]).then(([result]) => {
      if (active) { setStatus(result); setExpired(false); }
    }).catch(reason => { if (active) reportError(reason); });
    return () => { active = false; };
  }, [open, verified, reload, state.loadList, reportError]);

  useEffect(() => {
    if (!open || !verified || !id) { setLoading(false); return; }
    let active = true;
    setLoading(true);
    state.loadConversation(id).catch(reason => {
      if (!active) return;
      if (reason instanceof KnowledgeRequestError && reason.status === 404) select('');
      else reportError(reason);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, verified, id, reload, state.loadConversation, select, reportError]);

  useEffect(() => {
    if (!open || !verified || expired || !id || !pending || state.pendingById[id]) return;
    const timer = window.setInterval(() => state.loadConversation(id).catch(reportError), 2000);
    return () => window.clearInterval(timer);
  }, [open, verified, expired, id, pending, state.pendingById, state.loadConversation, reportError]);

  useEffect(() => {
    if (open) messages.current?.scrollTo({ top: messages.current.scrollHeight, behavior: 'instant' });
  }, [open, id, detail?.turns, pending]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || question.length > 2000 || pending || submitting.current || !available || (id && !detail)) return;
    submitting.current = true;
    setError('');
    let targetId = id;
    try {
      if (!targetId) {
        setCreating(true);
        targetId = await state.createConversation();
        select(targetId);
      }
    } catch (reason) {
      reportError(reason);
      return;
    } finally {
      submitting.current = false;
      setCreating(false);
    }
    setDrafts(current => ({ ...current, [id]: '', [targetId]: '' }));
    try {
      await state.sendQuestion(targetId, question);
    } catch (reason) {
      setDrafts(current => ({ ...current, [targetId]: current[targetId] || question }));
      if (reason instanceof KnowledgeRequestError && reason.status === 401) setExpired(true);
    }
  }

  function newConversation() {
    select('');
    input.current?.focus();
  }

  return <div className="floating-knowledge">
    {open && <section ref={panel} id="floating-knowledge-panel" className={`fk-panel${resizing ? ' is-resizing' : ''}`} style={panelHeight === null ? undefined : { height: panelHeight }} role="dialog" aria-modal="false" aria-labelledby="fk-title">
      <div className="fk-resize-handle" role="separator" tabIndex={0} aria-label="调整问答窗口高度" aria-orientation="horizontal" aria-valuemin={Math.round(minHeight)} aria-valuemax={Math.round(maxHeight)} aria-valuenow={Math.round(currentHeight)} aria-valuetext={`${Math.round(currentHeight)} 像素`} title="上下拖动调整高度，双击恢复半屏"
        onPointerDown={event => {
          if (event.button !== 0 || !event.isPrimary) return;
          event.preventDefault();
          event.currentTarget.focus();
          event.currentTarget.setPointerCapture(event.pointerId);
          resizeDrag.current = { pointerId: event.pointerId, y: event.clientY, height: panel.current?.getBoundingClientRect().height ?? currentHeight };
          setResizing(true);
        }}
        onPointerMove={event => {
          const drag = resizeDrag.current;
          if (drag?.pointerId === event.pointerId) setPanelHeight(clampHeight(drag.height + drag.y - event.clientY));
        }}
        onPointerUp={() => { resizeDrag.current = null; setResizing(false); }}
        onPointerCancel={() => { resizeDrag.current = null; setResizing(false); }}
        onLostPointerCapture={() => { resizeDrag.current = null; setResizing(false); }}
        onDoubleClick={() => setPanelHeight(null)}
        onKeyDown={event => {
          if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          setPanelHeight(clampHeight(event.key === 'Home' ? minHeight : event.key === 'End' ? maxHeight : currentHeight + (event.key === 'ArrowUp' ? 24 : -24)));
        }} />
      <header className="fk-header">
        <div className="fk-identity"><span className="fk-avatar"><Headphones size={20} /></span><div><h2 id="fk-title">知识库问答</h2><p>{pending && verified && !expired ? '正在查找资料并回答' : '从收藏的文章中寻找答案'}</p></div></div>
        <div className="fk-actions">
          {verified && !expired && <>
            <button type="button" title="新建会话" aria-label="新建会话" disabled={creating} onClick={newConversation}><Plus size={18} /></button>
            <div className="fk-history-control" ref={historyControl}>
              <button ref={historyButton} type="button" title="历史会话" aria-label="历史会话" aria-expanded={historyOpen} aria-controls="fk-history-list" disabled={creating} onClick={() => setHistoryOpen(value => !value)}><History size={17} /></button>
              {historyOpen && <div id="fk-history-list" className="fk-history-list" style={{ maxHeight: Math.min(240, Math.max(0, currentHeight - 92)) }} role="group" aria-label="历史会话列表">
                <div className="fk-history-label">历史会话</div>
                <button type="button" onClick={newConversation} aria-current={!id ? 'true' : undefined}><Plus size={13} /><span>新会话</span></button>
                {id && !state.conversations.some(item => item.id === id) && <button type="button" aria-current="true" onClick={() => select(id)}><span>{detail?.conversation.title || '上次的会话'}</span></button>}
                {state.conversations.map(item => <button key={item.id} type="button" aria-current={id === item.id ? 'true' : undefined} onClick={() => select(item.id)} title={item.title}><span>{item.title}</span></button>)}
                {state.conversations.length === 0 && !id && <p>提问后，会话会保存在这里。</p>}
                {state.conversations.length < state.total && <button type="button" onClick={() => state.loadList(false).catch(reportError)}><span>加载更多会话</span></button>}
              </div>}
            </div>
            <a href={id ? `/admin/ask?conversation=${encodeURIComponent(id)}` : '/admin/ask'} target="_blank" rel="noopener noreferrer" title="打开完整问答页" aria-label="打开完整问答页"><ExternalLink size={16} /></a>
          </>}
          <button ref={closeButton} type="button" onClick={close} aria-label="收起问答侧栏" title="收起"><X size={19} /></button>
        </div>
      </header>
      {adminStatus === 'checking' ? <div className="fk-welcome" role="status"><Loader2 size={22} className="animate-spin" /><p>正在连接知识库…</p></div> : !verified || expired ? <div className="fk-welcome"><BookOpenText size={32} strokeWidth={1.4} /><h3>登录后，向文章库提问</h3><p>查找观点、理解概念，回答附有原文引用。</p><a className="fk-login" href="/admin" target="_blank" rel="noopener noreferrer">登录管理后台 <ExternalLink size={14} /></a><small>登录完成后，回到这里继续提问。</small></div> : <>
        <div className="fk-messages" ref={messages} aria-label="问答记录" aria-busy={pending || loading}>
          {error && <div className="fk-notice" role="alert"><span>{error}</span><button type="button" onClick={() => setReload(value => value + 1)}><RefreshCw size={13} />重试</button></div>}
          {status?.message && <div className="fk-notice"><span>{status.message}</span><a href="/admin/model" target="_blank" rel="noopener noreferrer">配置模型</a></div>}
          {id && loading && !detail ? <div className="fk-welcome" role="status"><Loader2 size={22} className="animate-spin" /><p>加载会话…</p></div> : !detail?.turns.length ? <div className="fk-welcome"><BookOpenText size={32} strokeWidth={1.4} /><h3>有什么想了解的？</h3><p>围绕已保存的文章提问，<br />也可以对比观点、继续追问。</p><button className="fk-suggestion" type="button" onClick={() => { setDrafts(current => ({ ...current, [id]: 'KV Cache 如何减少重复计算？' })); input.current?.focus(); }}>试试：KV Cache 如何减少重复计算？ <ArrowUp size={14} /></button></div> : detail.turns.map(turn => <article className="fk-turn" key={turn.id}>
            <div className="fk-question"><span>你</span><p>{turn.question}</p></div>
            <div className="fk-response"><span className="knowledge-speaker"><BookOpenText size={13} />SynthAI</span>{turn.status === 'completed' ? <Suspense fallback={<p className="knowledge-pending">正在显示回答…</p>}><KnowledgeAnswer turn={turn} /></Suspense> : turn.status === 'pending' ? <p className="knowledge-pending" role="status"><Loader2 size={15} className="animate-spin" />正在查找资料并生成回答…</p> : <div className="fk-notice"><span>{turn.error_message || '回答已中断，请重新提问。'}</span><button type="button" onClick={() => { setDrafts(current => ({ ...current, [id]: turn.question })); input.current?.focus(); }}>重新提问</button></div>}</div>
          </article>)}
        </div>
        <div className="fk-composer-wrap">
          {state.errorsById[id] && <p className="fk-send-error" role="alert">{state.errorsById[id]}</p>}
          <form className="fk-composer" onSubmit={event => void submit(event)}>
            <textarea ref={input} aria-label="向知识库提问" value={draft} maxLength={2000} rows={2} disabled={creating} placeholder="输入问题，查找文章中的答案…" onChange={event => setDrafts(current => ({ ...current, [id]: event.target.value }))} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />
            <div className="fk-composer-bottom"><span>{pending ? '可以收起，回答会继续生成' : 'Enter 发送 · Shift + Enter 换行'}</span><button type="submit" aria-label="发送问题" disabled={!draft.trim() || pending || creating || !available || Boolean(id && !detail)}>{pending || creating ? <Loader2 size={17} className="animate-spin" /> : <ArrowUp size={19} />}</button></div>
          </form>
          <p className="fk-footnote">回答基于文章片段，请结合原文核对</p>
        </div>
      </>}
    </section>}
    <button ref={launcher} type="button" className={`fk-launcher${open ? ' is-open' : ''}`} tabIndex={open ? -1 : 0} aria-hidden={open || undefined} aria-label={open ? '收起知识库问答' : '打开知识库问答'} aria-expanded={open} aria-controls="floating-knowledge-panel" onClick={() => open ? close() : setOpen(true)} title="知识库问答">{open ? <X size={24} /> : <MessageCircle size={25} strokeWidth={1.8} />}{!open && pending && verified && <span className="fk-busy" aria-label="正在回答" />}</button>
  </div>;
}
