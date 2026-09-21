import { useEffect, useMemo } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import ArticleList from '../components/ArticleList';
import { useAppStore } from '../../app/store/useAppStore';

export default function Articles() {
  const articles = useAppStore((state) => state.articles);
  const fetchArticles = useAppStore((state) => state.fetchArticles);
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q')?.trim() || '';

  useEffect(() => { void fetchArticles(); }, [fetchArticles]);

  const filteredArticles = useMemo(() => {
    if (!query) return articles;
    const normalizedQuery = query.toLocaleLowerCase();
    return articles.filter((article) => [
      article.title,
      article.summary,
      article.original_url,
      article.source_type,
    ].some((value) => value.toLocaleLowerCase().includes(normalizedQuery)));
  }, [articles, query]);

  return (
    <div>
      <section className="admin-top">
        <div>
          <div className="eyebrow">Library / 02</div>
          <h1>文章库</h1>
          <p>{query ? `正在筛选包含“${query}”的文章。` : '按生成时间整理的全部内容，点击卡片进入独立阅读页。'}</p>
        </div>
        <Link to="/" className="secondary-button">返回发现 <ArrowUpRight size={14} /></Link>
      </section>
      <section className="article-section">
        <div className="section-heading"><div><h2>{query ? '搜索结果' : '最近整理'}</h2><p>共 {filteredArticles.length} 篇文章。</p></div></div>
        <ArticleList articles={filteredArticles} emptyMessage={query ? '没有找到匹配的文章，请换个关键词试试。' : undefined} />
      </section>
    </div>
  );
}
