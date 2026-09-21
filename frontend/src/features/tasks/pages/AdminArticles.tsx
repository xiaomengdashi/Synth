import { useEffect } from 'react';
import { ArrowUpRight, ArrowRight, FileText, Trash2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
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
  const { articles, fetchArticles, deleteArticle } = useAppStore();
  const navigate = useNavigate();
  useEffect(() => { void fetchArticles(); }, [fetchArticles]);

  return (
    <div>
      <AdminPageHeader eyebrow="Library / 02" title="文章管理" description="管理前台文章库中的内容，查看、删除或进入独立阅读页。" actions={<Link to="/articles" className="secondary-button">打开前台文章库 <ArrowUpRight size={14} /></Link>} />
      <section className="admin-section">
        <div className="section-heading"><div><h2>全部文章</h2><p>共 {articles.length} 篇内容。</p></div></div>
        <div className="task-list">
          {articles.length === 0 ? <div className="empty-state">还没有保存文章。</div> : articles.map((article) => (
            <div
              className="task-row article-management-row"
              key={article.id}
              role="link"
              tabIndex={0}
              onClick={() => navigate(`/article/${article.id}`)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  navigate(`/article/${article.id}`);
                }
              }}
            >
              <div className="task-main"><span className="task-icon"><FileText size={14} /></span><div className="task-copy"><strong>{article.title}</strong><span>{getSourceLabel(article.source_type)} · {formatDistanceToNow(new Date(article.created_at))}前</span></div></div>
              <div className="task-actions"><ArrowRight className="article-row-arrow" size={15} /><button className="tiny-button" type="button" onClick={(event) => { event.stopPropagation(); void deleteArticle(article.id); }} aria-label="删除文章"><Trash2 size={12} /></button></div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
