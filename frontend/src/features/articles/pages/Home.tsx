import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, Star, Tags } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import ArticleList, { sourceLabel } from '../components/ArticleList';
import ImportPanel from '../components/ImportPanel';
import type { Article } from '../types';

export default function Home() {
  const [recent, setRecent] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const version = useAppStore(state => state.statsVersion);
  const articlesVersion = useAppStore(state => state.articlesTotal);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch('/api/v1/articles?limit=20&offset=0')
      .then(res => { if (!res.ok) throw new Error(); return res.json(); })
      .then(data => { if (!cancelled) { setRecent(data.data); setTotal(data.total); setError(false); } })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [version, articlesVersion, reload]);
  const continuing = recent.filter(a => a.read_progress > 0.05 && a.read_progress < 0.95).slice(0, 3);
  return (
    <div className="reading-home">
      <header className="workspace-heading">
        <div><p className="eyebrow">我的知识库</p><h1>今天，接着读。</h1></div>
        <Link className="text-link" to="/articles">全部文章 <span className="workspace-count">{total}</span><ArrowRight size={15} /></Link>
      </header>
      <ImportPanel />
      <div className="home-content-layout">
        <section id="latest-articles" className="recent-section">
          <div className="section-heading"><div><h2>最近导入</h2><p>新收进来的内容，都在这里。</p></div><Link className="text-link" to="/articles">查看全部 <ArrowRight size={14} /></Link></div>
          {error ? <div className="empty-state">文章暂时加载失败。<button className="secondary-button" onClick={() => setReload(v => v + 1)}>重新加载</button></div>
            : <ArticleList articles={recent.slice(0, 8)} mode="list" emptyMessage={loading ? '正在加载文章…' : '还没有文章。在上方粘贴链接，保存第一篇内容。'} />}
        </section>
        <div className="home-reading-sidebar">
      {continuing.length > 0 && <section className="continue-section">
        <div className="section-heading"><div><h2>继续阅读</h2><p>最近读到这里</p></div><BookOpen size={19} /></div>
        <div className="continue-grid">{continuing.map(a => <Link to={`/article/${a.id}`} className="continue-item" key={a.id}>
          <span className="continue-source">{sourceLabel(a.source_type)}</span><h3>{a.title}</h3>
          <div className="continue-progress"><span style={{ width: `${Math.round(a.read_progress * 100)}%` }} /></div>
          <span className="continue-foot">已读 {Math.round(a.read_progress * 100)}% <ArrowRight size={14} /></span>
        </Link>)}</div>
      </section>}
        <aside className="home-shortcuts" aria-label="阅读快捷入口">
          <p className="eyebrow">我的阅读</p>
          <Link to="/articles?starred=1"><Star size={18} /><div><strong>星标文章</strong><span>留给值得再读的内容</span></div><ArrowRight size={14} /></Link>
          <Link to="/articles"><Tags size={18} /><div><strong>按分类浏览</strong><span>在文章库中整理与查找</span></div><ArrowRight size={14} /></Link>
          <div className="home-reading-note"><BookOpen size={20} /><p>读到一半也没关系。<br />下次打开，会回到上次的位置。</p></div>
        </aside>
        </div>
      </div>
    </div>
  );
}
