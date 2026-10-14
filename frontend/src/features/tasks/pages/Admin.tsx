import { useEffect, useState } from 'react';
import { Activity, ArrowRight, CheckCircle2, FileText, Mail, Settings2, Smartphone, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import ImportPanel from '../../articles/components/ImportPanel';
import { sourceLabel } from '../../articles/components/ArticleList';
import type { Article } from '../../articles/types';
import type { Account } from '../../tikhub/types';
import { money, requestJson } from '../../tikhub/client';
import { formatDistanceToNow } from '../../../utils/formatDate';
import { summarizeTaskStep } from '../taskPresentation';

export default function Admin() {
  const { tasks, fetchTasks, statsVersion } = useAppStore();
  const articlesVersion = useAppStore(state => state.articlesTotal);
  const [articles, setArticles] = useState<Article[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [accountLoading, setAccountLoading] = useState(true);
  const [articlesError, setArticlesError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/articles?limit=5&offset=0').then(res => { if (!res.ok) throw new Error(); return res.json(); })
      .then(data => { if (!cancelled) { setArticles(data.data); setTotal(data.total); setArticlesError(false); } })
      .catch(() => { if (!cancelled) setArticlesError(true); });
    return () => { cancelled = true; };
  }, [statsVersion, articlesVersion]);
  useEffect(() => {
    void fetchTasks();
    const timer = window.setInterval(() => void fetchTasks(), 5000);
    return () => window.clearInterval(timer);
  }, [fetchTasks]);
  useEffect(() => {
    let cancelled = false;
    requestJson<Account>('/api/v1/tikhub/account').then(data => { if (!cancelled) setAccount(data); })
      .catch(() => {}).finally(() => { if (!cancelled) setAccountLoading(false); });
    return () => { cancelled = true; };
  }, []);
  const active = tasks.filter(t => t.status === 'processing' || t.status === 'pending');
  const failed = tasks.filter(t => t.status === 'failed');
  const attention = [...active, ...failed].slice(0, 4);
  return (
    <div className="admin-workspace">
      <header className="ac-workspace-heading"><div><p className="eyebrow">SynthAI 控制台</p><h1>工作台</h1><p>导入内容，查看进度，整理你的知识库。</p></div><Link className="ac-btn secondary" to="/admin/articles">管理文章 <ArrowRight size={15} /></Link></header>
      <div className="workspace-metrics">
        <Link to="/admin/articles"><FileText size={18} /><span>已保存文章<strong>{total ?? '—'}<small>篇</small></strong></span></Link>
        <Link to="/admin/tasks"><Activity size={18} /><span>处理中<strong>{active.length}<small>条</small></strong></span></Link>
        <Link to="/admin/tasks"><span className={`metric-dot ${failed.length ? 'has-errors' : ''}`} /><span>失败任务<strong>{failed.length}<small>条</small></strong></span></Link>
        <Link to="/admin/tikhub"><Wallet size={18} /><span>TikHub 余额<strong>{accountLoading ? '…' : account?.configured ? money(account.user?.balance) : '—'}</strong></span></Link>
      </div>
      <div className="admin-work-grid">
        <div className="admin-work-main">
          <section className="work-section"><div className="work-section-heading"><h2>快速导入</h2><span>粘贴链接，直接开始</span></div><ImportPanel /></section>
          <section className="work-section"><div className="work-section-heading"><h2>需要关注 <span className="work-count">{active.length + failed.length}</span></h2><Link to="/admin/tasks">全部任务 <ArrowRight size={14} /></Link></div>
            {attention.length ? <div className="work-task-list">{attention.map(task => <Link to="/admin/tasks" key={task.id} className="work-task">
              <span className={`ac-badge ${task.status === 'failed' ? 'danger' : 'processing'}`}>{task.status === 'failed' ? '失败' : task.status === 'pending' ? '排队中' : '处理中'}</span>
              <div><strong>{task.original_url}</strong><p>{summarizeTaskStep(task.current_step || '等待处理')}</p></div><ArrowRight size={15} />
            </Link>)}</div> : <div className="work-empty"><CheckCircle2 size={22} /><div><strong>暂时没有需要处理的任务</strong><p>提交链接后，可以在这里查看处理状态。</p></div></div>}
          </section>
          <section className="work-section"><div className="work-section-heading"><h2>最近入库</h2><Link to="/admin/articles">全部文章 <ArrowRight size={14} /></Link></div>
            {articlesError ? <p className="ac-empty">文章加载失败，请稍后刷新。</p> : articles.length ? <div className="work-article-list">{articles.map(article => <Link to={`/article/${article.id}`} className="work-article" key={article.id}><div><strong>{article.title}</strong><span>{sourceLabel(article.source_type)} · {article.category || '未分类'}</span></div><time>{formatDistanceToNow(new Date(article.created_at))}</time><ArrowRight size={14} /></Link>)}</div> : <p className="ac-empty">{total === null ? '正在加载…' : '还没有文章，在上方导入第一条链接。'}</p>}
          </section>
        </div>
        <aside className="admin-work-aside">
          <section className="work-side-section"><p className="eyebrow">更多导入方式</p><Link to="/admin/email"><Mail size={18} /><div><strong>邮箱导入</strong><span>收取邮件中的内容</span></div><ArrowRight size={14} /></Link><Link to="/admin/share"><Smartphone size={18} /><div><strong>手机分享</strong><span>在手机上随手保存</span></div><ArrowRight size={14} /></Link></section>
          <section className="work-side-section"><p className="eyebrow">服务状态</p><div className="service-status"><span className={`metric-dot ${account?.configured ? 'is-ready' : ''}`} /><strong>TikHub 数据服务</strong></div><p className="work-side-copy">{accountLoading ? '正在检查账户…' : account?.configured ? '已配置，可用于微信、X 和 B 站内容导入。' : account === null ? '暂时无法读取账户信息。' : '尚未配置，设置后即可导入平台内容。'}</p><Link className="service-settings" to="/admin/tikhub"><Settings2 size={15} />管理服务配置 <ArrowRight size={14} /></Link></section>
          <section className="work-side-section"><p className="eyebrow">整理内容</p><Link to="/admin/categories"><div><strong>维护文章分类</strong><span>让内容更容易找到</span></div><ArrowRight size={14} /></Link><Link to="/admin/notes"><div><strong>回顾划线笔记</strong><span>留住阅读时的想法</span></div><ArrowRight size={14} /></Link></section>
        </aside>
      </div>
    </div>
  );
}
