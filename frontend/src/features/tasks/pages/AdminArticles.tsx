import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { ArrowUpRight, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import ArticleListFooter from '../../articles/components/ArticleListFooter';
import { adminFetch } from '../../../utils/adminAuth';
import { formatDistanceToNow } from '../../../utils/formatDate';
import type { Article } from '../../articles/types';

function getSourceLabel(sourceType: Article['source_type']) {
  if (sourceType === 'wechat') return '微信公众号';
  if (sourceType === 'bilibili') return 'Bilibili';
  if (sourceType === 'x') return 'X / Twitter';
  return '网页链接';
}

export default function AdminArticles() {
  const { articles, articlesTotal, articlesLoading, fetchArticles, deleteArticle, updateArticle, pushToast } = useAppStore();
  const [categories, setCategories] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState('all');
  const [src, setSrc] = useState('all');
  useEffect(() => { void fetchArticles({ reset: true, all: true }); }, [fetchArticles]);

  const filtering = query.trim() !== '' || cat !== 'all' || src !== 'all';

  // 筛选/搜索是纯前端过滤,必须等全量文章到位才不漏结果;浏览态走渐进加载
  useEffect(() => {
    if (filtering && !articlesLoading) void fetchArticles({ reset: true, all: true });
  }, [filtering, articlesLoading, fetchArticles]);

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

  const filtered = useMemo(() => {
    let list = articles;
    if (cat === '__none') list = list.filter((article) => !(article.category || '').trim());
    else if (cat !== 'all') list = list.filter((article) => (article.category || '').trim() === cat);
    if (src !== 'all') {
      list = list.filter((article) => (src === '__other'
        ? !['wechat', 'x', 'bilibili'].includes(article.source_type)
        : article.source_type === src));
    }
    const keyword = query.trim().toLowerCase();
    if (keyword) {
      list = list.filter((article) => [article.title, article.original_url]
        .some((value) => (value || '').toLowerCase().includes(keyword)));
    }
    return list;
  }, [articles, query, cat, src]);

  return (
    <div>
      <AdminPageHeader
        summary={<span>{filtering ? `共 ${articlesTotal || articles.length} 篇 · 筛选出 ${filtered.length} 篇` : `共 ${articlesTotal || articles.length} 篇内容`}</span>}
        actions={<>
          <label className="ac-search" style={{ width: 220 }} aria-label="搜索文章">
            <Search size={14} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题或链接" />
          </label>
          <Link to="/articles" className="ac-btn secondary sm">打开前台文章库 <ArrowUpRight size={13} /></Link>
        </>}
      />
      <section className="ac-card">
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
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
                <tr><td colSpan={5}><div className="ac-empty">{articlesLoading ? '正在加载文章…' : '还没有保存文章。'}</div></td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={5}><div className="ac-empty">没有符合筛选条件的文章，换个条件试试。</div></td></tr>
              ) : filtered.map((article) => (
                <tr key={article.id}>
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
                  <td className="cell-time">{formatDistanceToNow(new Date(article.created_at))}前</td>
                  <td>
                    <div className="ac-row-actions">
                      <button className="ac-btn danger-ghost sm" type="button" onClick={() => void deleteArticle(article.id)} aria-label={`删除「${article.title}」`}><Trash2 size={13} />删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtering && articles.length > 0 && <ArticleListFooter emptyCount={articles.length} />}
      </section>
    </div>
  );
}
