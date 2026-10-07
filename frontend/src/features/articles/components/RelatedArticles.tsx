import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { CSSProperties } from 'react';
import type { Article } from '../types';
import { sourceColor, sourceLabel } from './ArticleList';
import { formatAbsolute } from '../../../utils/formatDate';

/**
 * 相关阅读:详情页正文之后的紧凑推荐行。接口无数据时整块不渲染,加载中不占位(静默出现)。
 * hasToc:文章带侧栏目录时(≥1280px 横排布局),内容让出目录列与阅读卡对齐。
 */
export default function RelatedArticles({ articleId, hasToc = false }: { articleId: string; hasToc?: boolean }) {
  const [related, setRelated] = useState<Article[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/articles/${articleId}/related`)
      .then((res) => (res.ok ? res.json() : { data: [] }))
      .then((payload: { data?: Article[] }) => {
        if (!cancelled) setRelated(Array.isArray(payload.data) ? payload.data : []);
      })
      .catch(() => { /* 推荐是锦上添花,失败静默不渲染 */ });
    return () => { cancelled = true; };
  }, [articleId]);

  if (related.length === 0) return null;

  return (
    <section className={`related-block ${hasToc ? 'has-toc' : ''}`.trim()} aria-label="相关阅读">
      <div className="related-inner">
        <h2 className="related-title">相关阅读</h2>
        <div className="related-rows">
          {related.map((item) => (
            <Link
              key={item.id}
              to={`/article/${item.id}`}
              className="related-row"
              style={{ '--src': sourceColor(item.source_type) } as CSSProperties}
            >
              <span className="related-row-main">
                <strong>{item.title}</strong>
                <p>{item.summary}</p>
              </span>
              <span className="related-row-meta">
                <span className="meta-source"><i />{sourceLabel(item.source_type)}</span>
                <time>{formatAbsolute(new Date(item.created_at))}</time>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
