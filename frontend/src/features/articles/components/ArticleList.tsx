import { SOURCE_META } from '../lib/contentSources';
import { ArrowRight, Star } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { CSSProperties } from 'react';
import type { Article } from '../types';
import { formatAbsolute } from '../../../utils/formatDate';
import { isRead } from '../lib/readingState';
import { useAppStore } from '../../app/store/useAppStore';

export function sourceLabel(sourceType: Article['source_type']) {
  return SOURCE_META[sourceType]?.label ?? '网页';
}

/** 来源功能色:微信绿 / X 蓝 / B 站粉,其余归墨色。 */
export function sourceColor(sourceType: Article['source_type']) {
  if (sourceType === 'wechat') return 'var(--wechat)';
  if (sourceType === 'x') return 'var(--x-blue)';
  if (sourceType === 'bilibili') return 'var(--bili)';
  return 'var(--faint)';
}

function srcStyle(sourceType: Article['source_type']): CSSProperties {
  return { '--src': sourceColor(sourceType), '--chip': sourceColor(sourceType) } as CSSProperties;
}

function Cover({ article, kind }: { article: Article; kind: 'card' | 'row' }) {
  if (article.cover_image_url) {
    return (
      <span className={kind === 'card' ? 'article-cover' : 'article-row-cover'}>
        <img src={article.cover_image_url} alt="" loading="lazy" />
      </span>
    );
  }
  return (
    <span className={kind === 'card' ? 'article-cover' : 'article-row-cover'}>
      <span className="article-cover-fallback">{sourceLabel(article.source_type)}</span>
    </span>
  );
}

/** 收藏/取消收藏:嵌在行/卡可点区内,先拦下链接跳转只翻转标记;Toast 反馈成败。 */
function StarButton({ article }: { article: Article }) {
  const toggleStar = useAppStore((state) => state.toggleStar);
  const pushToast = useAppStore((state) => state.pushToast);
  const starred = article.is_starred === true;

  const handle = async (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const next = !starred;
    const ok = await toggleStar(article.id, next);
    pushToast({ title: ok ? (next ? '已加入收藏' : '已取消收藏') : '收藏操作失败，请稍后重试', tone: ok ? 'success' : 'error' });
  };

  return (
    <button
      type="button"
      className={`star-toggle ${starred ? 'starred' : ''}`}
      aria-pressed={starred}
      aria-label={starred ? '取消收藏' : '收藏'}
      title={starred ? '取消收藏' : '收藏'}
      onClick={handle}
    >
      <Star size={14} fill={starred ? 'currentColor' : 'none'} />
    </button>
  );
}

/** 已读徽:进度 ≥ 0.95 前端派生,不占后端列。 */
function ReadBadge() {
  return <span className="read-badge">已读</span>;
}

export default function ArticleList({
  articles,
  mode = 'grid',
  emptyMessage,
}: {
  articles: Article[];
  mode?: 'grid' | 'list';
  emptyMessage?: string;
}) {
  if (articles.length === 0) {
    return <div className="empty-state">{emptyMessage || '还没有文章。粘贴一条链接，开始建立你的第一篇知识卡片。'}</div>;
  }

  if (mode === 'list') {
    return (
      <div className="article-rows">
        {articles.map((article, index) => (
          <div key={article.id} className="anim-enter" style={{ '--lift': '10px', animationDelay: `${Math.min(index, 12) * .035}s` } as CSSProperties}>
            <Link to={`/article/${article.id}`} className="article-row" style={srcStyle(article.source_type)}>
              <Cover article={article} kind="row" />
              <span className="article-row-main">
                <h3>{article.title}</h3>
                <p>{article.summary}</p>
              </span>
              <span className="article-row-side">
                <span className="article-row-flags">
                  {isRead(article.read_progress) ? <ReadBadge /> : null}
                  <StarButton article={article} />
                </span>
                <span className="meta-source"><i />{sourceLabel(article.source_type)}</span>
                <time>{formatAbsolute(new Date(article.created_at))}</time>
              </span>
            </Link>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="article-grid">
      {articles.map((article, index) => (
        <article
          key={article.id}
          className="article-card anim-enter"
          style={{ ...srcStyle(article.source_type), '--lift': '12px', animationDelay: `${Math.min(index, 12) * .04}s` } as CSSProperties}
        >
            <Link to={`/article/${article.id}`} className="article-cover" tabIndex={-1} aria-hidden="true">
              {article.cover_image_url
                ? <img src={article.cover_image_url} alt="" loading="lazy" />
                : <span className="article-cover-fallback">{sourceLabel(article.source_type)}</span>}
            </Link>
            <div className="article-body">
              <Link to={`/article/${article.id}`} style={{ textDecoration: 'none' }}><h3>{article.title}</h3></Link>
              <p>{article.summary}</p>
              <div className="article-meta">
                <span className="meta-source"><i />{sourceLabel(article.source_type)} · {formatAbsolute(new Date(article.created_at))}</span>
                <span className="meta-side">
                  {isRead(article.read_progress) ? <ReadBadge /> : null}
                  <StarButton article={article} />
                  <span className="read-arrow"><ArrowRight size={13} /></span>
                </span>
              </div>
            </div>
          </article>
        ))}
      </div>
    );
}
