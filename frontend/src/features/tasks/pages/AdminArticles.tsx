import { useEffect, useState } from 'react';
import { ArrowUpRight, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import { formatDistanceToNow } from '../../../utils/formatDate';
import type { Article } from '../../articles/types';

function getSourceLabel(sourceType: Article['source_type']) {
  if (sourceType === 'wechat') return '微信公众号';
  if (sourceType === 'bilibili') return 'Bilibili';
  if (sourceType === 'x') return 'X / Twitter';
  return '网页链接';
}

export default function AdminArticles() {
  const { articles, fetchArticles, deleteArticle, pushToast } = useAppStore();
  const [categories, setCategories] = useState<string[]>([]);
  useEffect(() => { void fetchArticles(); }, [fetchArticles]);

  useEffect(() => {
    fetch('/api/v1/categories')
      .then((res) => (res.ok ? res.json() : { names: [] }))
      .then((data: { names?: string[] }) => setCategories(data.names ?? []))
      .catch(() => setCategories([]));
  }, []);

  const changeCategory = async (articleId: string, title: string, value: string) => {
    try {
      const res = await fetch(`/api/v1/articles/${articleId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: value }),
      });
      if (!res.ok) throw new Error('patch failed');
      await fetchArticles();
      pushToast({ title: `「${title.slice(0, 14)}${title.length > 14 ? '…' : ''}」分类已保存`, tone: 'success' });
    } catch {
      pushToast({ title: '分类保存失败，请稍后重试', tone: 'error' });
    }
  };

  return (
    <div>
      <AdminPageHeader
        summary={<span>共 {articles.length} 篇内容</span>}
        actions={<Link to="/articles" className="ac-btn secondary sm">打开前台文章库 <ArrowUpRight size={13} /></Link>}
      />
      <section className="ac-card">
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>文章</th>
                <th>来源</th>
                <th>分类</th>
                <th>保存时间</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {articles.length === 0 ? (
                <tr><td colSpan={5}><div className="ac-empty">还没有保存文章。</div></td></tr>
              ) : articles.map((article) => (
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
                      onChange={(event) => void changeCategory(article.id, article.title, event.target.value)}
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
      </section>
    </div>
  );
}
