import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { CSSProperties } from 'react';
import type { Article } from '../types';
import { formatAbsolute } from '../../../utils/formatDate';

export function sourceLabel(sourceType: Article['source_type']) {
  if (sourceType === 'wechat') return '微信公众号';
  if (sourceType === 'bilibili') return 'Bilibili';
  if (sourceType === 'x') return 'X / Twitter';
  if (sourceType === 'douyin') return '抖音';
  return '网页';
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
                <span className="read-arrow"><ArrowRight size={13} /></span>
              </div>
            </div>
          </article>
        ))}
      </div>
    );
}
