import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, LocateFixed, PenLine } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { formatDistanceToNow } from '../../../utils/formatDate';
import { MAX_QUOTE_LENGTH, hasSameQuote } from '../lib/noteAnchoring';
import {
  applyDocumentHighlights,
  applyShadowHighlights,
  buildAnchorFromSelection,
  clearDocumentHighlights,
  collectTextBlocks,
  flashDocumentRange,
  flashShadowNote,
  getActiveRangeInRoot,
  rangesForNotes,
  unwrapShadowHighlights,
} from '../lib/noteHighlight';

interface NoteRow {
  id: string;
  article_id: string;
  quote: string;
  note: string;
  prefix: string;
  suffix: string;
  created_at: string;
}

interface NoteAnchor {
  quote: string;
  prefix: string;
  suffix: string;
}

/** 事件目标是否落在自家浮层(工具条/输入卡/气泡)内。closest 对已脱离文档的节点同样
 * 有效——click 派发中 React 可能已卸载浮层,ref.contains 会误判成外部点击 */
function isOwnOverlay(target: EventTarget | null | undefined): boolean {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest('.note-select-bar, .note-composer, .note-popover'));
}

/**
 * 划线笔记:详情页选中正文文字→浮动工具条「添加划线」→小输入卡保存;
 * 重进按文本锚定恢复高亮(主文档走 CSS Custom Highlight,微信 shadow 走 span 包裹,
 * 机制见 lib/noteHighlight.ts 顶部注释),正文下方「划线笔记」列表可定位回原文。
 * 空数据不渲染列表区(循 RelatedArticles 惯例)。
 */
export default function ArticleNotes({
  articleId,
  contentRoot,
  contentVersion,
  hasToc = false,
}: {
  articleId: string;
  contentRoot: () => Element | ShadowRoot | null;
  /** 内容根被整体重写后的信号(微信 shadow innerHTML 重写),递增以触发重画 */
  contentVersion: number;
  hasToc?: boolean;
}) {
  const pushToast = useAppStore((state) => state.pushToast);

  const [notes, setNotes] = useState<NoteRow[]>([]);
  const [anchoredIds, setAnchoredIds] = useState<Set<string>>(new Set());
  const [toolbar, setToolbar] = useState<{ left: number; top: number } | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);
  // 输入卡位置在打开瞬间定格:选区随后塌陷(点进 textarea)只收工具条,不带走输入卡
  const [composerPos, setComposerPos] = useState<{ left: number; top: number } | null>(null);
  const [pendingAnchor, setPendingAnchor] = useState<NoteAnchor | null>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [popover, setPopover] = useState<{ note: NoteRow; left: number; top: number } | null>(null);

  const rangesRef = useRef<Map<string, Range[]>>(new Map());
  // mouseup 时定格的锚点(quote+前后文指纹):Chromium/Edge 154 起 shadow 内真实选区从
  // document.getSelection() 只能拿到净化视图;且点击工具条按钮的 mousedown 会把
  // shadow 选区塌陷(preventDefault 无效),锚点必须在 mouseup 当场捕获,不能等 click
  const activeAnchorRef = useRef<NoteAnchor | null>(null);
  const savingRef = useRef(false);
  const composerOpenRef = useRef(false);
  composerOpenRef.current = composerOpen;

  // 读取该文章的全部划线笔记(读者级,失败静默:附属数据不阻塞阅读)。
  // articleId 变化先清空:store 命中完整数据时 ArticleNotes 不卸载,不清会把
  // 旧文章的笔记/高亮错挂到新文章正文上(拉取失败时永久错挂)。
  useEffect(() => {
    let cancelled = false;
    setNotes([]);
    setAnchoredIds(new Set());
    rangesRef.current = new Map();
    fetch(`/api/v1/notes?article_id=${encodeURIComponent(articleId)}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((payload: { total: number; data?: NoteRow[] }) => {
        if (!cancelled) setNotes(Array.isArray(payload.data) ? payload.data : []);
      })
      .catch(() => { /* 划线笔记是附属数据,失败静默 */ });
    return () => { cancelled = true; };
  }, [articleId]);

  // 恢复高亮:对每条笔记做文本锚定后按路径绘制。setTimeout(0) 推迟到 hljs 改写
  // pre code 之后(先画的 Range 会随 innerHTML 重写失效,文本不变重匹配自愈)。
  useEffect(() => {
    const root = contentRoot();
    if (!root || notes.length === 0) {
      clearDocumentHighlights();
      return;
    }
    const timer = window.setTimeout(() => {
      // shadow 路径必须先拆旧包裹 span、在干净 DOM 上算 Range,再重包:
      // unwrap 的 parent.normalize() 会合并旧 wrap 时 splitText 出的文本节点,
      // 带着旧 span 先算好的 Range 会随节点合并失联而被静默丢弃(旧高亮消失)
      if (root instanceof ShadowRoot) unwrapShadowHighlights(root);
      const map = rangesForNotes(notes, root);
      rangesRef.current = map;
      setAnchoredIds(new Set(map.keys()));
      if (root instanceof ShadowRoot) applyShadowHighlights(root, map);
      else applyDocumentHighlights(map);
    }, 0);
    return () => { window.clearTimeout(timer); };
  }, [articleId, notes, contentRoot, contentVersion]);

  // 卸载时清理注册表(主文档高亮注册在 CSS.highlights 上,不随 DOM 消失)
  useEffect(() => () => { clearDocumentHighlights(); }, []);

  // 工具条定位:选区区间取视口矩形,上方居中;越界钳到视口内
  const placeToolbar = useCallback((range: Range): { left: number; top: number } | null => {
    const rect = range.getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) return null;
    const left = Math.min(Math.max(rect.left + rect.width / 2, 90), Math.max(window.innerWidth - 90, 90));
    const top = Math.max(rect.top - 44, 8);
    return { left, top };
  }, []);

  // 划线入口:mouseup/touchend 后取「完整落在内容根内」的活选区才出工具条。
  // 取区间走 getActiveRangeInRoot:Chromium/Edge 154 对 shadow 内真实选区只回净化视图,
  // 旧接口判定(isCollapsed/contains)会全部失败——必须经 getComposedRanges 取回真区间。
  // 锚点与区间在 mouseup 当场定格:按钮 mousedown 会塌陷 shadow 选区,click 时已取不到
  useEffect(() => {
    const onSelectionEnd = (event?: Event) => {
      if (composerOpenRef.current) return;
      // 工具条/输入卡自身的 mouseup 不是「选区结束」:它先于 click 触发,此时选区可能
      // 已被 mousedown 塌陷,先收工具条会让按钮在 click 到达前被卸载、点击丢失
      if (isOwnOverlay(event?.target)) return;
      const root = contentRoot();
      const range = getActiveRangeInRoot(root);
      if (!root || !range) {
        setToolbar(null);
        return;
      }
      const position = placeToolbar(range);
      const anchor = position ? buildAnchorFromSelection(collectTextBlocks(root), range) : null;
      if (!position || !anchor || !anchor.quote.trim()) {
        setToolbar(null);
        return;
      }
      activeAnchorRef.current = anchor;
      setToolbar(position);
    };
    document.addEventListener('mouseup', onSelectionEnd);
    // 触屏选区(长按选词)不触发 mouseup,补 touchend 同管线(未在真机实测)
    document.addEventListener('touchend', onSelectionEnd);
    return () => {
      document.removeEventListener('mouseup', onSelectionEnd);
      document.removeEventListener('touchend', onSelectionEnd);
    };
  }, [contentRoot, placeToolbar]);

  // 注:不监听 selectionchange——净化视图引擎下 isCollapsed 恒真不可判,且点击工具条
  // 按钮的 mousedown 会塌陷选区、selectionchange 先把工具条卸载导致 click 丢失。
  // 收起路径由 document click / mouseup(无活选区)/ 滚动 / Escape 覆盖

  // 滚动后 fixed 工具条与新视口位置脱节:选区还活着就按新矩形重定位,否则收起
  useEffect(() => {
    const onScroll = () => {
      setToolbar((current) => {
        if (!current) return current;
        const range = getActiveRangeInRoot(contentRoot());
        return range ? placeToolbar(range) : null;
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [contentRoot, placeToolbar]);

  // 点高亮看笔记:shadow 走 composedPath 找 [data-note-id];主文档 ::highlight 不改
  // hit-testing,用 caretRangeFromPoint 取点击位置逐笔记 Range 命中。气泡只读展示。
  useEffect(() => {
    const findClickedNote = (event: MouseEvent): NoteRow | null => {
      const path = event.composedPath();
      for (const node of path) {
        if (node instanceof Element && node.hasAttribute('data-note-id')) {
          const note = notes.find((item) => item.id === node.getAttribute('data-note-id'));
          if (note) return note;
        }
      }
      let caret: Range | null = null;
      if (typeof document.caretRangeFromPoint === 'function') {
        caret = document.caretRangeFromPoint(event.clientX, event.clientY);
      } else if (typeof document.caretPositionFromPoint === 'function') {
        const position = document.caretPositionFromPoint(event.clientX, event.clientY);
        if (position) {
          caret = document.createRange();
          caret.setStart(position.offsetNode, position.offset);
          caret.collapse(true);
        }
      }
      if (!caret) return null;
      for (const [noteId, ranges] of rangesRef.current) {
        for (const range of ranges) {
          try {
            if (range.compareBoundaryPoints(Range.START_TO_START, caret) <= 0
              && range.compareBoundaryPoints(Range.END_TO_END, caret) >= 0) {
              return notes.find((item) => item.id === noteId) || null;
            }
          } catch { /* 跨树比较抛错时跳过该条 */ }
        }
      }
      return null;
    };
    const onClick = (event: MouseEvent) => {
      // 自家浮层内的点击不处理:必须用 closest 判定而非 ref.contains——click 派发中
      // React 可能已先行处理并卸载了工具条(ref 变 null),此时误判「外部点击」会把
      // 刚打开的输入卡在同一任务内又关掉(composer 挂了就卸,肉眼只见工具条消失)
      if (isOwnOverlay(event.target)) return;
      // 拖选结束也会补发一次 click(落在 mousedown/mouseup 目标的公共祖先上):
      // 此时选区还活着,不能清刚由 mouseup 呈现的工具条,也不开气泡。
      // 判定走 getActiveRangeInRoot——净化视图下旧接口取不到 shadow 内活选区
      const selectionActive = Boolean(getActiveRangeInRoot(contentRoot()));
      if (selectionActive) return;
      const clickedNote = findClickedNote(event);
      setComposerOpen(false);
      setToolbar(null);
      if (clickedNote) {
        const left = Math.min(Math.max(event.clientX - 24, 12), Math.max(window.innerWidth - 356, 12));
        const top = Math.min(event.clientY + 14, Math.max(window.innerHeight - 150, 12));
        setPopover({ note: clickedNote, left, top });
      } else {
        setPopover(null);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPopover(null);
        setComposerOpen(false);
        setToolbar(null);
      }
    };
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('click', onClick);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [notes, contentRoot]);

  const closeComposer = () => {
    setComposerOpen(false);
    setComposerPos(null);
    setToolbar(null);
    setPendingAnchor(null);
    setNoteDraft('');
    activeAnchorRef.current = null;
  };

  // 点击「添加划线」:用 mouseup 当场定格的锚点(按钮 mousedown 会塌陷 shadow 选区,
  // click 时活选区已不可靠),重复/超长前置拦截
  const handleStartCompose = () => {
    const anchor = activeAnchorRef.current;
    if (!anchor) {
      pushToast({ title: '请选中正文文字后再添加划线', tone: 'error' });
      return;
    }
    if (hasSameQuote(notes, anchor.quote)) {
      pushToast({ title: '这段文字已有划线笔记', tone: 'error' });
      setToolbar(null);
      return;
    }
    if (anchor.quote.length > MAX_QUOTE_LENGTH) {
      pushToast({ title: `选中文字过长（最多 ${MAX_QUOTE_LENGTH} 字），请缩短后重试`, tone: 'error' });
      return;
    }
    setPendingAnchor(anchor);
    setNoteDraft('');
    setComposerPos(toolbar ? { ...toolbar } : { left: Math.max(window.innerWidth / 2, 90), top: 90 });
    setComposerOpen(true);
  };

  const handleSave = async () => {
    if (!pendingAnchor || savingRef.current) return;
    const text = noteDraft.trim();
    if (!text) {
      pushToast({ title: '笔记内容不能为空', tone: 'error' });
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const response = await fetch('/api/v1/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          article_id: articleId,
          quote: pendingAnchor.quote,
          note: text,
          prefix: pendingAnchor.prefix,
          suffix: pendingAnchor.suffix,
        }),
      });
      if (response.status === 409) {
        pushToast({ title: '这段文字已有划线笔记', tone: 'error' });
        closeComposer();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const saved = (await response.json()) as NoteRow;
      setNotes((prev) => [...prev, saved]);
      pushToast({ title: '划线笔记已保存', tone: 'success' });
      document.getSelection()?.removeAllRanges();
      closeComposer();
    } catch {
      pushToast({ title: '划线笔记保存失败，请稍后重试', tone: 'error' });
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  // 定位:滚动到划线首 Range 居中并闪烁 1.6s(主文档第二注册名,shadow 临时换 span 底色)
  const handleLocate = (note: NoteRow) => {
    const ranges = rangesRef.current.get(note.id);
    if (!ranges || ranges.length === 0) return;
    const rect = ranges[0].getBoundingClientRect();
    window.scrollTo({ top: Math.max(0, rect.top + window.scrollY - window.innerHeight / 2), behavior: 'smooth' });
    const root = contentRoot();
    if (root instanceof ShadowRoot) flashShadowNote(root, note.id);
    else flashDocumentRange(ranges[0]);
  };

  return (
    <>
      {toolbar && !composerOpen ? (
        <div
          className="note-select-bar"
          style={{ left: toolbar.left, top: toolbar.top }}
          role="toolbar"
          aria-label="划线操作"
        >
          {/* mousedown preventDefault 保选区:默认行为会先塌陷选区再触发 click */}
          <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={handleStartCompose}>
            <PenLine size={13} /> 添加划线
          </button>
        </div>
      ) : null}

      {composerOpen && composerPos && pendingAnchor ? (
        <div
          className="note-composer"
          style={{ left: composerPos.left, top: composerPos.top }}
          role="dialog"
          aria-label="添加划线笔记"
        >
          <p className="note-composer-quote">{pendingAnchor.quote}</p>
          <textarea
            value={noteDraft}
            onChange={(event) => setNoteDraft(event.target.value)}
            placeholder="写下这段文字的笔记…"
            aria-label="笔记内容"
            autoFocus
          />
          <div className="note-composer-actions">
            <button type="button" className="secondary-button" onClick={closeComposer} disabled={saving}>取消</button>
            <button type="button" className="primary-button" onClick={() => void handleSave()} disabled={saving}>
              {saving ? <><Loader2 size={14} className="animate-spin" />保存中</> : '保存'}
            </button>
          </div>
        </div>
      ) : null}

      {popover ? (
        <div
          className="note-popover"
          style={{ left: popover.left, top: popover.top }}
          role="dialog"
          aria-label="划线笔记内容"
        >
          <p className="note-popover-quote">{popover.note.quote}</p>
          <p className="note-popover-note">{popover.note.note}</p>
          <span className="note-popover-time">{formatDistanceToNow(new Date(popover.note.created_at))}</span>
        </div>
      ) : null}

      {notes.length > 0 ? (
        <section className={`notes-block ${hasToc ? 'has-toc' : ''}`.trim()} aria-label="划线笔记">
          <div className="notes-inner">
            <h2 className="notes-title">划线笔记</h2>
            <div className="notes-rows">
              {notes.map((note) => (
                <div className="note-row" key={note.id}>
                  <p className="note-row-quote">{note.quote}</p>
                  <p className="note-row-note">{note.note}</p>
                  <div className="note-row-meta">
                    <time>{formatDistanceToNow(new Date(note.created_at))}</time>
                    {anchoredIds.has(note.id) ? (
                      <button type="button" className="note-locate" onClick={() => handleLocate(note)}>
                        <LocateFixed size={12} />定位
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </>
  );
}
