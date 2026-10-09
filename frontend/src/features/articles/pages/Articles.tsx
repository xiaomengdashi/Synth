import { useEffect, useMemo, useState } from 'react';
import { LayoutGrid, List, Star } from 'lucide-react';
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
  const articlesLoading = useAppStore((state) => state.articlesLoading);
  const fetchArticles = useAppStore((state) => state.fetchArticles);
  const articlesTotal = useAppStore((state) => state.articlesTotal);
  const [sourceCounts, setSourceCounts] = useState<{ wechat: number; x: number; bilibili: number; other: number } | null>(null);
  const [starredCount, setStarredCount] = useState<number | null>(null);

  // 空闲时预取详情页 chunk:列表页停留时间长,预取后点开文章零等待
  useEffect(() => {
    const prefetch = () => { void import('./Article'); };
    (window.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 1500)))(prefetch);
  }, []);

  // 来源/收藏计数在挂载与 statsVersion 变化时拉取:滚动续载/排序不改变分布,
  // 但收藏翻转会——store 里 +1 版本号驱动这里重拉,让「只看收藏 N」即时准确
  const statsVersion = useAppStore((state) => state.statsVersion);
  useEffect(() => {
    fetch('/api/v1/articles/stats')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        setSourceCounts(data?.sources ?? null);
        setStarredCount(typeof data?.starred === 'number' ? data.starred : null);
      })
      .catch(() => {
        setSourceCounts(null);
        setStarredCount(null);
      });
  }, [statsVersion]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [view, setView] = useState<ViewMode>(() => (localStorage.getItem('articles-view') === 'grid' ? 'grid' : 'list'));
  const [sort, setSort] = useState<SortOrder>(() => (localStorage.getItem('articles-sort') === 'old' ? 'old' : 'new'));
  useEffect(() => { localStorage.setItem('articles-view', view); }, [view]);
  useEffect(() => { localStorage.setItem('articles-sort', sort); }, [sort]);

  const query = searchParams.get('q')?.trim() || '';
  const source = searchParams.get('source') || 'all';
  const starredOnly = searchParams.get('starred') === '1';

  // 筛选/搜索由后端完成;与 store 记录的已加载参数组合对比,不一致就(重)取——
  // 即使某次 reset 请求被进行中的续载吞掉,续载结束后本 effect 也会自动补发
  const articlesLoadedKey = useAppStore((state) => state.articlesLoadedKey);
  const articlesErrorKey = useAppStore((state) => state.articlesErrorKey);
  // 与 fetchArticles 成功/失败时登记的 key 同构:category 恒空段|source|q|starred
  const currentKey = `|${source === 'all' ? '' : source}|${query}|${starredOnly ? '1' : ''}`;
  const loadFailed = articlesErrorKey === currentKey;
  useEffect(() => {
    if (articlesLoading) return;
    if (articlesLoadedKey === currentKey) return;
    // 同一筛选失败后不再自动重试(否则失败→清 loading→再请求会无限循环),换筛选即可重新加载
    if (articlesErrorKey === currentKey) return;
    void fetchArticles({ reset: true, source: source === 'all' ? undefined : source, q: query || undefined, starred: starredOnly || undefined });
  }, [fetchArticles, source, query, starredOnly, articlesLoading, articlesLoadedKey, articlesErrorKey, currentKey]);

  const sortedArticles = useMemo(() => {
    const factor = sort === 'new' ? -1 : 1;
    // 展示层兜底:收藏视图下过滤掉 store 里已被取消收藏的行(toggleStar 只 patch 不过滤数组)
    const visible = starredOnly ? articles.filter((a) => a.is_starred !== false) : articles;
    return [...visible].sort((a, b) => factor * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()));
  }, [articles, sort, starredOnly]);

  const applySource = (next: string) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'all') params.delete('source');
    else params.set('source', next);
    setSearchParams(params, { replace: true });
  };

  const applyStarred = (next: boolean) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.set('starred', '1');
    else params.delete('starred');
    setSearchParams(params, { replace: true });
  };

  const activeFilterLabel = source === 'all' ? null : sourceLabel(source as Article['source_type']);
  const filtering = Boolean(query) || source !== 'all' || starredOnly;

  return (
    <div>
      <section className="page-head">
        <div>
          <h1>文章库</h1>
          <p>{query ? `正在筛选包含“${query}”的文章。` : '按时间整理的全部收藏内容。'}</p>
        </div>
        <span className="section-count">{filtering ? `筛选出 ${articlesTotal} 篇` : `共 ${articlesTotal} 篇`}</span>
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
          <button
            type="button"
            className={`filter-chip star-filter ${starredOnly ? 'active' : ''}`}
            aria-pressed={starredOnly}
            onClick={() => applyStarred(!starredOnly)}
          >
            <Star size={13} />只看收藏<em>{starredCount ?? 0}</em>
          </button>
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
          articles={sortedArticles}
          mode={view}
          emptyMessage={articles.length === 0 && loadFailed
            ? '文章加载失败，请检查服务是否可用后刷新页面。'
            : articlesLoading && articles.length === 0
            ? '正在加载文章…'
            : query || activeFilterLabel || starredOnly
            ? starredOnly && !query && !activeFilterLabel
              ? '还没有收藏的文章。点亮列表或文章页的星标，稍后来这里接着读。'
              : `没有${activeFilterLabel ? `来自${activeFilterLabel}` : ''}${query && activeFilterLabel ? '且匹配关键词' : '匹配关键词'}${starredOnly && (query || activeFilterLabel) ? '且收藏' : ''}的文章，换个筛选试试。`
            : '还没有文章。粘贴一条链接，开始建立你的第一篇知识卡片。'}
        />
        <ArticleListFooter
          emptyCount={articles.length}
          source={source === 'all' ? undefined : source}
          q={query || undefined}
          starred={starredOnly || undefined}
        />
      </section>
    </div>
  );
}
