import { SOURCE_META, type Source } from '../lib/contentSources';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { BookOpen, ChevronDown, LayoutGrid, List, Search, Star, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import ArticleList, { sourceColor } from '../components/ArticleList';
import ArticleListFooter from '../components/ArticleListFooter';
import { useAppStore } from '../../app/store/useAppStore';

const SOURCES = Object.entries(SOURCE_META).map(([value, info]) => ({ value: value as Source, label: info.label }));

export default function Articles() {
  const { articles, articlesLoading, articlesTotal, fetchArticles, articlesLoadedKey, articlesErrorKey, statsVersion } = useAppStore();
  const [params, setParams] = useSearchParams();
  const query = params.get('q')?.trim() || '';
  const source = params.get('source') || '';
  const category = params.get('cat') || '';
  const starred = params.get('starred') === '1';
  const [search, setSearch] = useState(query);
  const [view, setView] = useState(() => localStorage.getItem('articles-view') === 'grid' ? 'grid' : 'list');
  const [sort, setSort] = useState(() => localStorage.getItem('articles-sort') === 'old' ? 'old' : 'new');
  const [names, setNames] = useState<string[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [stats, setStats] = useState<{ sources?: Record<string, number>; starred?: number } | null>(null);
  const [navigationError, setNavigationError] = useState(false);
  const [navReload, setNavReload] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => { setSearch(query); }, [query]);
  useEffect(() => { localStorage.setItem('articles-view', view); }, [view]);
  useEffect(() => { localStorage.setItem('articles-sort', sort); }, [sort]);
  useEffect(() => {
    let cancelled = false;
    const read = async (url: string) => { const res = await fetch(url); if (!res.ok) throw new Error(); return res.json(); };
    Promise.all([read('/api/v1/categories'), read('/api/v1/categories/counts'), read('/api/v1/articles/stats')])
      .then(([categories, totals, statistics]) => {
        if (cancelled) return;
        setNames(categories.names || []); setCounts({ ...totals.counts, __none: totals.uncategorized || 0 }); setStats(statistics); setNavigationError(false);
      }).catch(() => { if (!cancelled) setNavigationError(true); });
    return () => { cancelled = true; };
  }, [statsVersion, navReload]);
  const key = `${category === 'all' ? '' : category}|${source}|${query}|${starred ? '1' : ''}`;
  const options = { category: category && category !== 'all' ? category : undefined, source: source || undefined, q: query || undefined, starred: starred || undefined };
  const failed = articlesErrorKey === key;
  useEffect(() => {
    if (articlesLoading || articlesLoadedKey === key || articlesErrorKey === key) return;
    void fetchArticles({ reset: true, category: category && category !== 'all' ? category : undefined, source: source || undefined, q: query || undefined, starred: starred || undefined });
  }, [articlesLoading, articlesLoadedKey, articlesErrorKey, key, category, source, query, starred, fetchArticles]);
  const ready = articlesLoadedKey === key;
  const visible = useMemo(() => [...(ready ? articles : [])].filter(a => !starred || a.is_starred !== false)
    .sort((a, b) => (sort === 'new' ? -1 : 1) * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime())), [articles, ready, sort, starred]);
  const change = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setParams(next, { replace: true });
  };
  const toggleFilter = (name: 'cat' | 'source', value: string) => {
    change(name, params.get(name) === value ? '' : value);
  };
  const submitSearch = (event: FormEvent) => { event.preventDefault(); change('q', search.trim()); };
  const filtering = Boolean(query || source || (category && category !== 'all') || starred);
  const total = stats?.sources ? Object.values(stats.sources).reduce((sum, n) => sum + n, 0) : null;
  const categoryLabel = category === '__none' ? '未分类' : category === 'all' ? '' : category;
  return (
    <div className="library-workspace">
      <aside className={`library-sidebar ${filtersOpen ? 'is-open' : ''}`} aria-label="文章筛选">
        <button className="library-mobile-toggle" onClick={() => setFiltersOpen(!filtersOpen)} aria-expanded={filtersOpen} aria-controls="library-navigation">分类与来源 {filtering && <span className="filter-dot" />}<ChevronDown size={16} /></button>
        <div id="library-navigation" className="library-navigation">
          <p className="eyebrow">我的知识库</p>
          <button className={`library-nav-item library-scope ${!starred ? 'active' : ''}`} aria-pressed={!starred} onClick={() => setParams({})}><BookOpen size={16} /><span>全部文章</span><small>{total ?? '—'}</small></button>
          <button className={`library-nav-item library-scope ${starred ? 'active' : ''}`} aria-pressed={starred} onClick={() => change('starred', starred ? '' : '1')}><Star size={16} /><span>星标文章</span><small>{stats?.starred ?? '—'}</small></button>
          <div className="library-nav-group"><div className="library-group-heading"><h2>分类</h2></div>
            <button className={`library-nav-item ${!category || category === 'all' ? 'active' : ''}`} aria-label="显示全部分类" aria-pressed={!category || category === 'all'} onClick={() => change('cat', '')}><span>全部</span><small>{total ?? '—'}</small></button>
            {names.map(name => <button className={`library-nav-item ${category === name ? 'active' : ''}`} aria-pressed={category === name} title={name} key={name} onClick={() => toggleFilter('cat', name)}><span>{name}</span><small>{counts[name] ?? 0}</small></button>)}
            <button className={`library-nav-item ${category === '__none' ? 'active' : ''}`} aria-pressed={category === '__none'} onClick={() => toggleFilter('cat', '__none')}><span>未分类</span><small>{counts.__none ?? 0}</small></button>
          </div>
          <div className="library-nav-group"><div className="library-group-heading"><h2>来源</h2></div>
            <button className={`library-nav-item ${!source ? 'active' : ''}`} aria-label="显示全部来源" aria-pressed={!source} onClick={() => change('source', '')}><span>全部</span><small>{total ?? '—'}</small></button>
            {SOURCES.map(item => <button key={item.value} className={`library-nav-item ${source === item.value ? 'active' : ''}`} aria-pressed={source === item.value} onClick={() => toggleFilter('source', item.value)}><i className="library-source-dot" style={{ background: sourceColor(item.value) }} aria-hidden="true" /><span>{item.label}</span><small>{stats?.sources?.[item.value] ?? '—'}</small></button>)}
          </div>
          {navigationError && <button className="text-link" onClick={() => setNavReload(v => v + 1)}>筛选信息加载失败，重试</button>}
        </div>
      </aside>
      <div className="library-main">
        <header className="workspace-heading"><div><p className="eyebrow">阅读与收藏</p><h1>{categoryLabel || (starred ? '星标文章' : '文章库')}</h1></div><span className="section-count">{ready ? `${articlesTotal} 篇` : '正在查找…'}</span></header>
        <div className="library-toolbar">
          <form className="library-search" onSubmit={submitSearch}><Search size={17} /><input aria-label="搜索文章库" placeholder="搜索标题、摘要或链接" value={search} onChange={e => setSearch(e.target.value)} /><button type="submit">搜索</button></form>
          <div className="view-tools">
            <select className="library-sort" aria-label="文章排序" value={sort} onChange={e => setSort(e.target.value)}><option value="new">最新导入</option><option value="old">最早导入</option></select>
            <div className="seg" role="group" aria-label="切换视图"><button aria-label="列表视图" aria-pressed={view === 'list'} onClick={() => setView('list')}><List size={16} /></button><button aria-label="卡片视图" aria-pressed={view === 'grid'} onClick={() => setView('grid')}><LayoutGrid size={16} /></button></div>
          </div>
        </div>
        {filtering && <div className="active-filters"><span>当前筛选</span>{query && <button onClick={() => change('q', '')}>{query}<X size={12} /></button>}{categoryLabel && <button onClick={() => change('cat', '')}>{categoryLabel}<X size={12} /></button>}{source && <button onClick={() => change('source', '')}>{SOURCES.find(s => s.value === source)?.label || source}<X size={12} /></button>}{starred && <button onClick={() => change('starred', '')}>星标<X size={12} /></button>}<button className="clear-filters" onClick={() => setParams({})}>清空筛选</button></div>}
        {failed ? <div className="empty-state">文章加载失败。<button className="secondary-button" onClick={() => void fetchArticles({ reset: true, ...options })}>重新加载</button></div> : <>
          <ArticleList articles={visible} mode={view as 'list' | 'grid'} emptyMessage={!ready || articlesLoading ? '正在加载文章…' : filtering ? '没有匹配的文章，试试清空筛选或换个关键词。' : '还没有文章。回到首页，粘贴链接开始导入。'} />
          {ready && <ArticleListFooter emptyCount={visible.length} {...options} />}
        </>}
      </div>
    </div>
  );
}
