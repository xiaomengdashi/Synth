import { useEffect } from 'react';
import { ArrowRight, BarChart3, CheckCircle2, ListChecks, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import { formatDistanceToNow } from '../../../utils/formatDate';
import type { Article } from '../../articles/types';
import type { Task } from '../types';

const sourceLabels: Record<Article['source_type'], string> = {
  wechat: '微信公众号',
  x: 'X / Twitter',
  bilibili: 'Bilibili',
  douyin: '抖音',
  csdn: 'CSDN',
  cnblogs: '博客园',
  other: '其他来源',
};

const sourceColors = ['#70a835', '#b7f34b', '#ff8d54', '#91ae7e', '#a6b9ad', '#d7e0d8', '#53665a'];

function getDayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function getLastSevenDays() {
  const today = new Date();
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setHours(0, 0, 0, 0);
    date.setDate(today.getDate() - (6 - index));
    return date;
  });
}

function countArticlesByDay(articles: Article[]) {
  const days = getLastSevenDays();
  const counts = days.map((day) => articles.filter((article) => getDayKey(new Date(article.created_at)) === getDayKey(day)).length);
  return { days, counts };
}

function ArticleTrendChart({ articles }: { articles: Article[] }) {
  const { days, counts } = countArticlesByDay(articles);
  const chartWidth = 680;
  const chartHeight = 220;
  const padding = { top: 18, right: 18, bottom: 32, left: 28 };
  const maxCount = Math.max(...counts, 1);
  const xStep = (chartWidth - padding.left - padding.right) / (counts.length - 1);
  const yScale = (chartHeight - padding.top - padding.bottom) / maxCount;
  const points = counts.map((count, index) => `${padding.left + index * xStep},${chartHeight - padding.bottom - count * yScale}`).join(' ');
  const areaPoints = `${padding.left},${chartHeight - padding.bottom} ${points} ${chartWidth - padding.right},${chartHeight - padding.bottom}`;

  return (
    <div className="overview-chart overview-trend-chart">
      <div className="overview-chart-heading"><div><span className="eyebrow">Activity / 07</span><h2>内容增长趋势</h2></div><span className="chart-caption">近 7 天</span></div>
      <div className="chart-summary"><strong>{articles.length}</strong><span>篇累计内容</span><TrendingUp size={15} /></div>
      <svg className="trend-chart" viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label="近七天文章生成数量趋势图">
        {[0, 1, 2, 3].map((line) => {
          const y = padding.top + ((chartHeight - padding.top - padding.bottom) / 3) * line;
          return <line key={line} x1={padding.left} x2={chartWidth - padding.right} y1={y} y2={y} className="chart-grid-line" />;
        })}
        <polygon points={areaPoints} className="trend-area" />
        <polyline points={points} className="trend-line" />
        {counts.map((count, index) => {
          const x = padding.left + index * xStep;
          const y = chartHeight - padding.bottom - count * yScale;
          return <g key={getDayKey(days[index])}><circle cx={x} cy={y} r="4" className="trend-point" /><text x={x} y={chartHeight - 9} textAnchor="middle" className="chart-axis-label">{`${days[index].getMonth() + 1}/${days[index].getDate()}`}</text></g>;
        })}
      </svg>
    </div>
  );
}

function SourceBreakdown({ articles }: { articles: Article[] }) {
  const sourceCounts = Object.entries(sourceLabels)
    .map(([source, label]) => ({ source: source as Article['source_type'], label, count: articles.filter((article) => article.source_type === source).length }))
    .filter((item) => item.count > 0)
    .sort((a, b) => b.count - a.count);
  const total = articles.length || 1;

  return (
    <div className="overview-chart source-breakdown">
      <div className="overview-chart-heading"><div><span className="eyebrow">Sources / 08</span><h2>来源分布</h2></div><BarChart3 size={17} /></div>
      <div className="source-bar" aria-label="文章来源分布"><span className="source-bar-wechat" style={{ width: `${(sourceCounts.find((item) => item.source === 'wechat')?.count || 0) / total * 100}%` }} /><span className="source-bar-x" style={{ width: `${(sourceCounts.find((item) => item.source === 'x')?.count || 0) / total * 100}%` }} /><span className="source-bar-other" style={{ width: `${sourceCounts.filter((item) => item.source !== 'wechat' && item.source !== 'x').reduce((sum, item) => sum + item.count, 0) / total * 100}%` }} /></div>
      <div className="source-list">
        {sourceCounts.length === 0 ? <div className="chart-empty">还没有来源数据</div> : sourceCounts.map((item, index) => <div className="source-item" key={item.source}><span className="source-name"><i style={{ background: sourceColors[index] || sourceColors[sourceColors.length - 1] }} />{item.label}</span><strong>{item.count}<small>篇 · {Math.round(item.count / total * 100)}%</small></strong></div>)}
      </div>
    </div>
  );
}

function TaskStatusChart({ tasks }: { tasks: Task[] }) {
  const statuses = [
    { key: 'completed', label: '已完成', color: '#70a835' },
    { key: 'processing', label: '处理中', color: '#ff8d54' },
    { key: 'pending', label: '排队中', color: '#91ae7e' },
    { key: 'failed', label: '失败', color: '#d86546' },
  ];
  const total = tasks.length || 1;

  return (
    <div className="overview-chart task-status-chart">
      <div className="overview-chart-heading"><div><span className="eyebrow">Queue / 09</span><h2>任务状态</h2></div><ListChecks size={17} /></div>
      <div className="task-status-total"><strong>{tasks.length}</strong><span>条任务记录</span></div>
      <div className="status-bars">
        {statuses.map((status) => { const count = tasks.filter((task) => task.status === status.key).length; return <div className="status-bar-row" key={status.key}><div className="status-bar-label"><span>{status.label}</span><strong>{count}</strong></div><div className="status-bar-track"><span style={{ width: `${count / total * 100}%`, background: status.color }} /></div></div>; })}
      </div>
    </div>
  );
}

export default function Admin() {
  const { articles, tasks, config, fetchArticles, fetchTasks, fetchConfig } = useAppStore();
  useEffect(() => {
    void fetchArticles();
    void fetchTasks();
    void fetchConfig();
  }, [fetchArticles, fetchTasks, fetchConfig]);

  const completedCount = tasks.filter((task) => task.status === 'completed').length;
  const processingCount = tasks.filter((task) => task.status === 'processing' || task.status === 'pending').length;

  return (
    <div>
      <AdminPageHeader
        eyebrow="Operations / 01"
        title="内容总览"
        description="从内容增长、来源结构和任务状态，快速了解知识库的运行情况。"
        actions={<Link to="/" className="secondary-button accent">进入前台 <ArrowRight size={14} /></Link>}
      />

      <section className="admin-metrics" aria-label="数据概览">
        <div className="metric"><span>文章总数</span><strong>{articles.length}</strong><small>篇</small></div>
        <div className="metric"><span>已完成任务</span><strong>{completedCount}</strong><small>条</small></div>
        <div className="metric"><span>处理中</span><strong>{processingCount}</strong><small>{processingCount ? 'active' : 'idle'}</small></div>
        <div className="metric"><span>模型参数</span><strong style={{ fontSize: 17 }}>{config.modelName || '未设置'}</strong></div>
      </section>

      <section className="overview-chart-grid" aria-label="内容数据图表">
        <ArticleTrendChart articles={articles} />
        <SourceBreakdown articles={articles} />
        <TaskStatusChart tasks={tasks} />
      </section>

      <section className="admin-section overview-latest">
        <div className="section-heading"><div><div className="eyebrow">Latest / 10</div><h2>最近文章</h2><p>最近保存内容的快速入口。</p></div><Link className="text-link" to="/admin/articles">打开文章管理 <ArrowRight size={14} /></Link></div>
        <div className="task-list">
          {articles.slice(0, 5).map((article) => <Link className="task-row overview-article-row" to={`/article/${article.id}`} key={article.id}><div className="task-main"><span className="task-icon"><CheckCircle2 size={14} /></span><div className="task-copy"><strong>{article.title}</strong><span>{sourceLabels[article.source_type]} · {formatDistanceToNow(new Date(article.created_at))}前</span></div></div><ArrowRight size={15} /></Link>)}
          {articles.length === 0 ? <div className="empty-state">还没有保存文章。</div> : null}
        </div>
      </section>
    </div>
  );
}
