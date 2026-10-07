import { useEffect, useRef, useState } from 'react';
import { Loader2, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { adminFetch } from '../../../utils/adminAuth';
import { formatAbsolute } from '../../../utils/formatDate';

const PAGE_SIZE = 50;

interface AdminNoteRow {
  id: string;
  article_id: string;
  article_title: string | null;
  quote: string;
  note: string;
  created_at: string;
}

interface NotesPayload {
  total: number;
  data: AdminNoteRow[];
  articles: { id: string; title: string }[];
}

function fetchUrl(articleId: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (articleId !== 'all') params.set('article_id', articleId);
  return `/api/v1/notes/all?${params.toString()}`;
}

/**
 * 划线笔记管理:全量倒序表格,表头「文章」列嵌筛选下拉(先例:文章管理页)。
 * 移动端复用 ac-table-wrap 横滚——本页列少,不做文章管理的双布局。
 */
export default function AdminNotes() {
  const pushToast = useAppStore((state) => state.pushToast);
  const [rows, setRows] = useState<AdminNoteRow[]>([]);
  const [total, setTotal] = useState(0);
  const [articleFilter, setArticleFilter] = useState('all');
  const [articleOptions, setArticleOptions] = useState<{ id: string; title: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<AdminNoteRow | null>(null);
  const [deleting, setDeleting] = useState(false);
  // 正在加载的筛选(供续载落地时对比防串页)。不能用「参数没变就跳过」的 lastKey 守卫:
  // StrictMode 双调用会先清理首次请求(cancelled)再重跑,守卫在 ref 里看到参数相同而跳过,
  // 两次都没人落地结果,页面永久停在加载态(文章库页同病,e25915b 已修)
  const activeFilterRef = useRef('all');

  useEffect(() => {
    let cancelled = false;
    activeFilterRef.current = articleFilter;
    setLoading(true);
    adminFetch(fetchUrl(articleFilter, 0))
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((payload: NotesPayload) => {
        if (cancelled) return;
        setRows(Array.isArray(payload.data) ? payload.data : []);
        setTotal(payload.total || 0);
        setArticleOptions(Array.isArray(payload.articles) ? payload.articles : []);
      })
      .catch(() => {
        if (!cancelled) pushToast({ title: '划线笔记加载失败，请稍后重试', tone: 'error' });
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [articleFilter, pushToast]);

  const handleLoadMore = async () => {
    if (loadingMore) return;
    // 续载期间筛选可能已切换(筛选 effect 会整表重取):记录发起时的筛选,落地时不匹配即丢弃,
    // 否则旧筛选的行会 append 进新筛选列表并覆盖 total
    const filterAtStart = activeFilterRef.current;
    setLoadingMore(true);
    try {
      const res = await adminFetch(fetchUrl(filterAtStart, rows.length));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload: NotesPayload = await res.json();
      if (activeFilterRef.current !== filterAtStart) return;
      setRows((prev) => {
        const seen = new Set(prev.map((row) => row.id));
        return [...prev, ...payload.data.filter((row) => !seen.has(row.id))];
      });
      setTotal(payload.total || 0);
    } catch {
      if (activeFilterRef.current === filterAtStart) {
        pushToast({ title: '加载更多失败，请稍后重试', tone: 'error' });
      }
    } finally {
      setLoadingMore(false);
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    try {
      const res = await adminFetch(`/api/v1/notes/${pendingDelete.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRows((prev) => prev.filter((row) => row.id !== pendingDelete.id));
      setTotal((prev) => Math.max(0, prev - 1));
      pushToast({ title: '已删除该划线笔记', tone: 'success' });
      setPendingDelete(null);
    } catch {
      pushToast({ title: '删除失败，请稍后重试', tone: 'error' });
    } finally {
      setDeleting(false);
    }
  };

  const filtering = articleFilter !== 'all';
  const hasMore = rows.length < total;

  return (
    <div>
      <AdminPageHeader
        summary={filtering
          ? <span>筛选出 {rows.length} 条（本筛选共 {total} 条）</span>
          : <span>共 {total} 条划线笔记</span>}
      />

      <section className="ac-card">
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>
                  <select
                    className="ac-select th-select"
                    value={articleFilter}
                    onChange={(event) => setArticleFilter(event.target.value)}
                    aria-label="按文章筛选"
                    style={{ color: filtering ? 'var(--ac-accent)' : undefined }}
                  >
                    <option value="all">全部文章</option>
                    {articleOptions.map((item) => (
                      <option key={item.id} value={item.id}>{item.title}</option>
                    ))}
                  </select>
                </th>
                <th>划线片段</th>
                <th>笔记内容</th>
                <th>创建时间</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5}><div className="ac-empty">正在加载划线笔记…</div></td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={5}><div className="ac-empty">{filtering ? '没有该文章的划线笔记，换个条件试试。' : '还没有划线笔记。'}</div></td></tr>
              ) : rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <Link className="cell-main" to={`/article/${row.article_id}`}>{row.article_title || '未命名文章'}</Link>
                  </td>
                  <td>
                    <span className="cell-main" title={row.quote}>{row.quote}</span>
                  </td>
                  <td>
                    <span className="cell-main" title={row.note}>{row.note}</span>
                  </td>
                  <td className="cell-time">{formatAbsolute(new Date(row.created_at))}</td>
                  <td>
                    <div className="ac-row-actions">
                      <button
                        className="ac-btn danger-ghost sm"
                        type="button"
                        onClick={() => setPendingDelete(row)}
                        aria-label="删除该划线笔记"
                      >
                        <Trash2 size={13} />删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hasMore ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '14px 0 4px' }}>
            <button type="button" className="ac-btn ghost sm" onClick={() => void handleLoadMore()} disabled={loadingMore}>
              {loadingMore ? <><Loader2 size={13} className="animate-spin" />正在加载</> : <>加载更多（{rows.length}/{total}）</>}
            </button>
          </div>
        ) : null}
      </section>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="删除划线笔记"
        description={pendingDelete
          ? `确定删除划线「${pendingDelete.quote.slice(0, 24)}${pendingDelete.quote.length > 24 ? '…' : ''}」的笔记？删除后不可恢复。`
          : ''}
        confirmText="删除"
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}
