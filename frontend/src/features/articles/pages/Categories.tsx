import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ArticleList from '../components/ArticleList';
import { useAppStore } from '../../app/store/useAppStore';

/** 分类由后台维护;前台按分类浏览收藏的文章。 */
export default function Categories() {
  const articles = useAppStore((state) => state.articles);
  const fetchArticles = useAppStore((state) => state.fetchArticles);
  const [searchParams, setSearchParams] = useSearchParams();
  const [names, setNames] = useState<string[]>([]);

  const active = searchParams.get('cat') || 'all';

  useEffect(() => { void fetchArticles(); }, [fetchArticles]);

  useEffect(() => {
    fetch('/api/v1/categories')
      .then((res) => (res.ok ? res.json() : { names: [] }))
      .then((data: { names?: string[] }) => setNames(data.names ?? []))
      .catch(() => setNames([]));
  }, []);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const article of articles) {
      const key = (article.category || '').trim();
      if (key) map.set(key, (map.get(key) || 0) + 1);
    }
    return map;
  }, [articles]);

  const uncategorized = useMemo(
    () => articles.filter((article) => !(article.category || '').trim()).length,
    [articles],
  );

  const filtered = useMemo(() => {
    if (active === 'all') return articles;
    if (active === '__none') return articles.filter((article) => !(article.category || '').trim());
    return articles.filter((article) => (article.category || '').trim() === active);
  }, [articles, active]);

  const applyCat = (value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value === 'all') params.delete('cat');
    else params.set('cat', value);
    setSearchParams(params, { replace: true });
  };

  const activeLabel = active === 'all' ? null : active === '__none' ? '未分类' : active;

  return (
    <div>
      <section className="page-head">
        <div>
          <h1>分类</h1>
          <p>{names.length ? '按后台维护的分类浏览收藏内容。' : '还没有分类。到后台「系统配置 → 文章分类」添加，并在文章管理里为文章选择分类。'}</p>
        </div>
        <span className="section-count">共 {filtered.length} 篇</span>
      </section>

      {names.length > 0 ? (
        <section className="filter-bar">
          <div className="filter-chips" role="group" aria-label="按分类筛选">
            <button type="button" className={`filter-chip ${active === 'all' ? 'active' : ''}`} aria-pressed={active === 'all'} onClick={() => applyCat('all')}>
              全部<em>{articles.length}</em>
            </button>
            {names.map((name) => (
              <button key={name} type="button" className={`filter-chip ${active === name ? 'active' : ''}`} aria-pressed={active === name} onClick={() => applyCat(name)}>
                {name}<em>{counts.get(name) || 0}</em>
              </button>
            ))}
            {uncategorized > 0 ? (
              <button type="button" className={`filter-chip ${active === '__none' ? 'active' : ''}`} aria-pressed={active === '__none'} onClick={() => applyCat('__none')}>
                未分类<em>{uncategorized}</em>
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section>
        <ArticleList
          articles={filtered}
          mode="list"
          emptyMessage={activeLabel
            ? `「${activeLabel}」下还没有文章，到后台文章管理里为文章选择分类。`
            : '还没有文章。粘贴一条链接，开始建立你的第一篇知识卡片。'}
        />
      </section>
    </div>
  );
}
