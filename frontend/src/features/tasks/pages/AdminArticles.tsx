import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { ArrowUpRight, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { adminFetch } from '../../../utils/adminAuth';
import { formatAbsolute } from '../../../utils/formatDate';
import type { Article } from '../../articles/types';

function getSourceLabel(sourceType: Article['source_type']) {
  if (sourceType === 'wechat') return '微信公众号';
  if (sourceType === 'bilibili') return 'Bilibili';
  if (sourceType === 'x') return 'X / Twitter';
  return '网页链接';
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 700px)').matches);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 700px)');
    const onChange = (event: MediaQueryListEvent) => setIsMobile(event.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isMobile;
}

export default function AdminArticles() {
  const { articles, articlesTotal, articlesLoading, fetchArticles, deleteArticle, batchDeleteArticles, batchSetCategory, updateArticle, pushToast } = useAppStore();
  const [categories, setCategories] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState('all');
  const [src, setSrc] = useState('all');
  const isMobile = useIsMobile();
  const [pendingDelete, setPendingDelete] = useState<Article | null>(null);
  const [deleting, setDeleting] = useState(false);
  // 批量选择:筛选条件或列表内容变化后自动清掉已不在列表里的勾选
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const filtering = query.trim() !== '' || cat !== 'all' || src !== 'all';

  const someSelected = selected.size > 0;
  const allSelected = articles.length > 0 && articles.every((a) => selected.has(a.id));

  const toggleSelected = (articleId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(articleId)) next.delete(articleId);
      else next.add(articleId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected(allSelected ? new Set() : new Set(articles.map((a) => a.id)));
  };

  // 筛选/搜索走后端查询参数;参数没变不重取,加载中的变更等本轮结束自动补取(修掉旧的循环重取)
  const lastKey = useRef('');
  useEffect(() => {
    if (articlesLoading) return;
    const keyword = query.trim();
    const key = `${cat}|${src}|${keyword}`;
    if (lastKey.current === key) return;
    lastKey.current = key;
    void fetchArticles({
      reset: true,
      all: true,
      category: cat === 'all' ? undefined : cat,
      source: src === 'all' ? undefined : src,
      q: keyword || undefined,
    });
  }, [fetchArticles, cat, src, query, articlesLoading]);

  // 换筛选条件即放弃当前勾选;列表刷新后剔除已不存在的文章
  useEffect(() => { setSelected(new Set()); }, [cat, src, query]);
  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      const visible = new Set(articles.map((a) => a.id));
      const next = new Set([...prev].filter((id) => visible.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [articles]);

  useEffect(() => {
    fetch('/api/v1/categories')
      .then((res) => (res.ok ? res.json() : { names: [] }))
      .then((data: { names?: string[] }) => setCategories(data.names ?? []))
      .catch(() => setCategories([]));
  }, []);

  // 乐观更新:先改界面再存后端,失败自动回滚
  const changeCategory = (articleId: string, title: string, value: string) => {
    const previous = articles.find((a) => a.id === articleId)?.category ?? null;
    updateArticle(articleId, { category: value });
    const rollback = () => updateArticle(articleId, { category: previous });
    adminFetch(`/api/v1/articles/${articleId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: value }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('patch failed');
        pushToast({ title: `「${title.slice(0, 14)}${title.length > 14 ? '…' : ''}」分类已保存`, tone: 'success' });
      })
      .catch(() => {
        rollback();
        pushToast({ title: '分类保存失败，已恢复原分类', tone: 'error' });
      });
  };

  const handleBatchCategory = (value: string) => {
    const ids = [...selected];
    if (ids.length === 0) return;
    const label = value ? `移入「${value}」` : '设为未分类';
    void batchSetCategory(ids, value).then((ok) => {
      pushToast({ title: ok ? `已将 ${ids.length} 篇${label}` : '批量设置分类失败，请稍后重试', tone: ok ? 'success' : 'error' });
      if (ok) setSelected(new Set());
    });
  };

  return (
    <div>
      <AdminPageHeader
        summary={<span>{filtering ? `筛选出 ${articles.length} 篇（库内共 ${articlesTotal} 篇）` : `共 ${articlesTotal} 篇内容`}</span>}
        actions={<>
          <label className="ac-search" style={{ width: isMobile ? '100%' : 220 }} aria-label="搜索文章">
            <Search size={14} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题或链接" />
          </label>
          {isMobile ? (
            <>
              <select className="ac-select admin-filter-select" value={src} onChange={(event) => setSrc(event.target.value)} aria-label="按来源筛选">
                <option value="all">全部来源</option>
                <option value="wechat">微信公众号</option>
                <option value="x">X / Twitter</option>
                <option value="bilibili">Bilibili</option>
                <option value="__other">网页链接</option>
              </select>
              <select className="ac-select admin-filter-select" value={cat} onChange={(event) => setCat(event.target.value)} aria-label="按分类筛选">
                <option value="all">全部分类</option>
                <option value="__none">未分类</option>
                {categories.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </>
          ) : null}
          <Link to="/articles" className="ac-btn secondary sm">打开前台文章库 <ArrowUpRight size={13} /></Link>
        </>}
      />

      {someSelected ? (
        <div className="ac-batch-bar" role="toolbar" aria-label="批量操作">
          <strong>已选 <span className="ac-batch-count">{selected.size}</span> 篇</strong>
          <div className="ac-batch-actions">
            {isMobile ? (
              <button type="button" className="ac-btn ghost sm" onClick={toggleSelectAll}>{allSelected ? '全不选' : '全选'}</button>
            ) : null}
            <select className="ac-select" value="" onChange={(event) => handleBatchCategory(event.target.value)} aria-label="批量设置分类">
              <option value="" disabled hidden>批量设置分类</option>
              <option value="">未分类</option>
              {categories.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
            <button type="button" className="ac-btn danger-ghost sm" onClick={() => setBatchDeleting(true)}>
              <Trash2 size={13} />删除 {selected.size} 篇
            </button>
            <button type="button" className="ac-btn ghost sm" onClick={() => setSelected(new Set())}>取消选择</button>
          </div>
        </div>
      ) : null}

      {isMobile ? (
        <div className="ac-stack">
          {articles.length === 0 ? (
            <div className="ac-empty">{articles.length === 0 ? '还没有保存文章。' : '没有符合筛选条件的文章，换个条件试试。'}</div>
          ) : articles.map((article) => (
            <article key={article.id} className="ac-card article-card-m">
              <div className="ac-card-body">
                <Link className="cell-main" to={`/article/${article.id}`}>{article.title}</Link>
                <span className="cell-sub" title={article.original_url}>{article.original_url}</span>
                <div className="article-card-m-meta">
                  <input
                    className="ac-check"
                    type="checkbox"
                    checked={selected.has(article.id)}
                    onChange={() => toggleSelected(article.id)}
                    aria-label={`选择「${article.title}」`}
                  />
                  <span className="article-card-m-source">{getSourceLabel(article.source_type)}</span>
                  <select
                    className="ac-select"
                    value={article.category || ''}
                    onChange={(event) => changeCategory(article.id, article.title, event.target.value)}
                    aria-label={`选择「${article.title}」的分类`}
                  >
                    <option value="">未分类</option>
                    {categories.map((name) => <option key={name} value={name}>{name}</option>)}
                  </select>
                </div>
                <div className="article-card-m-foot">
                  <span className="cell-time">{formatAbsolute(new Date(article.created_at))}</span>
                  <button className="ac-btn danger-ghost sm" type="button" onClick={() => setPendingDelete(article)} aria-label={`删除「${article.title}」`}>
                    <Trash2 size={13} />删除
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
      <section className="ac-card">
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th className="ac-check-col">
                  <input
                    className="ac-check"
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => { if (el) el.indeterminate = someSelected && !allSelected; }}
                    onChange={toggleSelectAll}
                    aria-label="全选当前列表"
                  />
                </th>
                <th>文章</th>
                <th>
                  <select className="ac-select th-select" value={src} onChange={(event) => setSrc(event.target.value)} aria-label="按来源筛选" style={{ color: src !== 'all' ? 'var(--ac-accent)' : undefined }}>
                    <option value="all">全部来源</option>
                    <option value="wechat">微信公众号</option>
                    <option value="x">X / Twitter</option>
                    <option value="bilibili">Bilibili</option>
                    <option value="__other">网页链接</option>
                  </select>
                </th>
                <th>
                  <select className="ac-select th-select" value={cat} onChange={(event) => setCat(event.target.value)} aria-label="按分类筛选" style={{ color: cat !== 'all' ? 'var(--ac-accent)' : undefined }}>
                    <option value="all">全部分类</option>
                    <option value="__none">未分类</option>
                    {categories.map((name) => <option key={name} value={name}>{name}</option>)}
                  </select>
                </th>
                <th>保存时间</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {articles.length === 0 ? (
                <tr><td colSpan={6}><div className="ac-empty">还没有保存文章。</div></td></tr>
              ) : articles.length === 0 ? (
                <tr><td colSpan={6}><div className="ac-empty">没有符合筛选条件的文章，换个条件试试。</div></td></tr>
              ) : articles.map((article) => (
                <tr key={article.id}>
                  <td className="ac-check-col">
                    <input
                      className="ac-check"
                      type="checkbox"
                      checked={selected.has(article.id)}
                      onChange={() => toggleSelected(article.id)}
                      aria-label={`选择「${article.title}」`}
                    />
                  </td>
                  <td>
                    <Link className="cell-main" to={`/article/${article.id}`}>{article.title}</Link>
                    <span className="cell-sub" title={article.original_url}>{article.original_url}</span>
                  </td>
                  <td>{getSourceLabel(article.source_type)}</td>
                  <td>
                    <select
                      className="ac-select"
                      value={article.category || ''}
                      onChange={(event) => changeCategory(article.id, article.title, event.target.value)}
                      aria-label={`选择「${article.title}」的分类`}
                    >
                      <option value="">未分类</option>
                      {categories.map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                  </td>
                  <td className="cell-time">{formatAbsolute(new Date(article.created_at))}</td>
                  <td>
                    <div className="ac-row-actions">
                      <button className="ac-btn danger-ghost sm" type="button" onClick={() => setPendingDelete(article)} aria-label={`删除「${article.title}」`}><Trash2 size={13} />删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="删除文章"
        description={pendingDelete ? `确定删除「${pendingDelete.title}」？删除后不可恢复。` : ''}
        confirmText="删除"
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (!pendingDelete || deleting) return;
          setDeleting(true);
          // 成败提示由 store 的 deleteArticle 统一给出
          void deleteArticle(pendingDelete.id).then(() => {
            setDeleting(false);
            setPendingDelete(null);
          });
        }}
      />

      <ConfirmDialog
        open={batchDeleting}
        title="批量删除文章"
        description={batchDeleting ? `确定删除选中的 ${selected.size} 篇文章？删除后不可恢复。` : ''}
        confirmText={`删除 ${selected.size} 篇`}
        busy={batchBusy}
        onCancel={() => setBatchDeleting(false)}
        onConfirm={() => {
          if (batchBusy || selected.size === 0) return;
          const count = selected.size;
          const ids = [...selected];
          setBatchBusy(true);
          void batchDeleteArticles(ids).then((ok) => {
            setBatchBusy(false);
            setBatchDeleting(false);
            pushToast({ title: ok ? `已删除 ${count} 篇文章` : '批量删除失败，请稍后重试', tone: ok ? 'success' : 'error' });
            if (ok) setSelected(new Set());
          });
        }}
      />
    </div>
  );
}
