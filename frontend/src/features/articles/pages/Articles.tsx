import { useEffect, useMemo, useState } from 'react';
import { LayoutGrid, List } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import ArticleList, { sourceLabel } from '../components/ArticleList';
import ArticleListFooter from '../components/ArticleListFooter';
import type { Article } from '../types';
import { useAppStore } from '../../app/store/useAppStore';

type SourceFilter = 'wechat' | 'x' | 'bilibili';
type ViewMode = 'list' | 'grid';
type SortOrder = 'new' | 'old';

const FILTERS: { value: SourceFilter | 'all'; label: string; color?: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'wechat', label: '微信', color: 'var(--wechat)' },
  { value: 'x', label: 'X', color: 'var(--x-blue)' },
  { value: 'bilibili', label: 'B 站', color: 'var(--bili)' },
];

export default function Articles() {
  const articles = useAppStore((state) => state.articles);
  const fetchArticles = useAppStore((state) => state.fetchArticles);
  const articlesTotal = useAppStore((state) => state.articlesTotal);
  const [sourceCounts, setSourceCounts] = useState<{ wechat: number; x: number; bilibili: number; other: number } | null>(null);

  useEffect(() => {
    fetch('/api/v1/articles/stats')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setSourceCounts(data?.sources ?? null))
      .catch(() => setSourceCounts(null));
  }, [articles.length]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [view, setView] = useState<ViewMode>('list');
  const [sort, setSort] = useState<SortOrder>('new');

  const query = searchParams.get('q')?.trim() || '';
  const source = searchParams.get('source') || 'all';

  useEffect(() => { void fetchArticles({ reset: true, all: Boolean(source !== 'all' || query) }); }, [fetchArticles, source, query]);

  const filteredArticles = useMemo(() => {
    let list = articles;
    if (source !== 'all') list = list.filter((article) => article.source_type === source);
    if (query) {
      const normalizedQuery = query.toLocaleLowerCase();
      list = list.filter((article) => [
        article.title,
        article.summary,
        article.original_url,
        article.source_type,
      ].some((value) => (value || '').toLocaleLowerCase().includes(normalizedQuery)));
    }
    const factor = sort === 'new' ? -1 : 1;
    return [...list].sort((a, b) => factor * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()));
  }, [articles, source, query, sort]);

  const applySource = (next: string) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'all') params.delete('source');
    else params.set('source', next);
    setSearchParams(params, { replace: true });
  };

  const activeFilterLabel = source === 'all' ? null : sourceLabel(source as Article['source_type']);
  const filtering = Boolean(query) || source !== 'all';

  return (
    <div>
      <section className="page-head">
        <div>
          <h1>文章库</h1>
          <p>{query ? `正在筛选包含“${query}”的文章。` : '按时间整理的全部收藏内容。'}</p>
        </div>
        <span className="section-count">{filtering ? `筛选出 ${filteredArticles.length} 篇` : `共 ${articlesTotal} 篇`}</span>
      </section>

      <section className="filter-bar">
        <div className="filter-chips" role="group" aria-label="按来源筛选">
          {FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={`filter-chip ${source === filter.value ? 'active' : ''}`}
              aria-pressed={source === filter.value}
              style={filter.color ? ({ '--chip': filter.color } as React.CSSProperties) : undefined}
              onClick={() => applySource(filter.value)}
            >
              {filter.color ? <i /> : null}
              {filter.label}
              <em>{filter.value === 'all'
                ? (sourceCounts ? sourceCounts.wechat + sourceCounts.x + sourceCounts.bilibili + sourceCounts.other : articlesTotal)
                : (sourceCounts ? sourceCounts[filter.value as keyof typeof sourceCounts] : 0)}</em>
            </button>
          ))}
        </div>
        <div className="view-tools">
          <div className="seg" role="group" aria-label="切换视图">
            <button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')} title="列表视图"><List size={14} /></button>
            <button type="button" aria-pressed={view === 'grid'} onClick={() => setView('grid')} title="卡片视图"><LayoutGrid size={14} /></button>
          </div>
          <div className="seg" role="group" aria-label="切换排序">
            <button type="button" aria-pressed={sort === 'new'} onClick={() => setSort('new')}>最新</button>
            <button type="button" aria-pressed={sort === 'old'} onClick={() => setSort('old')}>最早</button>
          </div>
        </div>
      </section>

      <section>
        <ArticleList
          articles={filteredArticles}
          mode={view}
          emptyMessage={query || activeFilterLabel
            ? `没有${activeFilterLabel ? `来自${activeFilterLabel}` : ''}${query && activeFilterLabel ? '且匹配关键词' : '匹配关键词'}的文章，换个筛选试试。`
            : '还没有文章。粘贴一条链接，开始建立你的第一篇知识卡片。'}
        />
        {!query && source === 'all' ? <ArticleListFooter emptyCount={filteredArticles.length} /> : null}
      </section>
    </div>
  );
}
