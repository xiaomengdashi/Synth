import { useEffect, useState } from 'react';
import { BarChart3, CheckCircle2, FileText, ListChecks, Newspaper, Settings2, TrendingUp, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import { formatDistanceToNow } from '../../../utils/formatDate';
import { money, requestJson } from '../../tikhub/client';
import type { Account } from '../../tikhub/types';
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

const sourceColors = ['#16a34a', '#4ade80', '#f0a13c', '#38bdf8', '#a78bfa', '#94a3b8', '#64748b'];

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

function ArticleTrendChart({ articles, articlesTotal }: { articles: Article[]; articlesTotal: number }) {
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
    <div className="ac-card ac-span-2">
      <div className="ac-card-head">
        <h2 className="ac-card-title"><TrendingUp size={15} /> 内容增长趋势</h2>
        <span className="ac-card-caption">近 7 天</span>
      </div>
      <div className="ac-card-body">
        <div className="chart-summary"><strong>{Math.max(articlesTotal, articles.length)}</strong><span>篇累计内容</span><TrendingUp size={14} /></div>
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
    </div>
  );
}

function SourceBreakdown({ articles, sourceStats }: { articles: Article[]; sourceStats: { wechat: number; x: number; bilibili: number; other: number } | null }) {
  const sourceCounts = (sourceStats
    ? (Object.entries(sourceLabels) as [string, string][])
        .map(([source, label]) => ({ source: source as Article['source_type'], label, count: (sourceStats as Record<string, number>)[source] || 0 }))
        .filter((item) => item.count > 0)
    : Object.entries(sourceLabels)
        .map(([source, label]) => ({ source: source as Article['source_type'], label, count: articles.filter((article) => article.source_type === source).length }))
        .filter((item) => item.count > 0)
  ).sort((a, b) => b.count - a.count);
  const statTotal = sourceStats ? sourceStats.wechat + sourceStats.x + sourceStats.bilibili + sourceStats.other : 0;
  const total = statTotal || articles.length || 1;

  return (
    <div className="ac-card">
      <div className="ac-card-head">
        <h2 className="ac-card-title"><BarChart3 size={15} /> 来源分布</h2>
        <span className="ac-card-caption">{sourceCounts.length} 类来源</span>
      </div>
      <div className="ac-card-body">
        <div className="source-bar" aria-label="文章来源分布"><span className="source-bar-wechat" style={{ width: `${(sourceCounts.find((item) => item.source === 'wechat')?.count || 0) / total * 100}%` }} /><span className="source-bar-x" style={{ width: `${(sourceCounts.find((item) => item.source === 'x')?.count || 0) / total * 100}%` }} /><span className="source-bar-other" style={{ width: `${sourceCounts.filter((item) => item.source !== 'wechat' && item.source !== 'x').reduce((sum, item) => sum + item.count, 0) / total * 100}%` }} /></div>
        <div className="source-list">
          {sourceCounts.length === 0 ? <div className="chart-empty">还没有来源数据</div> : sourceCounts.map((item, index) => <div className="source-item" key={item.source}><span className="source-name"><i style={{ background: sourceColors[index] || sourceColors[sourceColors.length - 1] }} />{item.label}</span><strong>{item.count}<small>篇 · {Math.round(item.count / total * 100)}%</small></strong></div>)}
        </div>
      </div>
    </div>
  );
}

function TaskStatusChart({ tasks }: { tasks: Task[] }) {
  const statuses = [
    { key: 'completed', label: '已完成', color: '#16a34a' },
    { key: 'processing', label: '处理中', color: '#f0a13c' },
    { key: 'pending', label: '排队中', color: '#94a3b8' },
    { key: 'failed', label: '失败', color: '#ef4444' },
  ];
  const total = tasks.length || 1;

  return (
    <div className="ac-card">
      <div className="ac-card-head">
        <h2 className="ac-card-title"><ListChecks size={15} /> 任务状态</h2>
      </div>
      <div className="ac-card-body">
        <div className="task-status-total"><strong>{tasks.length}</strong><span>条任务记录</span></div>
        <div className="status-bars">
          {statuses.map((status) => { const count = tasks.filter((task) => task.status === status.key).length; return <div className="status-bar-row" key={status.key}><div className="status-bar-label"><span>{status.label}</span><strong>{count}</strong></div><div className="status-bar-track"><span style={{ width: `${count / total * 100}%`, background: status.color }} /></div></div>; })}
        </div>
      </div>
    </div>
  );
}

export default function Admin() {
  const { articles, tasks, fetchArticles, fetchTasks } = useAppStore();
  const articlesTotal = useAppStore((state) => state.articlesTotal);
  const [sourceStats, setSourceStats] = useState<{ wechat: number; x: number; bilibili: number; other: number } | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [accountLoading, setAccountLoading] = useState(true);
  useEffect(() => {
    void fetchArticles({ reset: true, all: true });
    fetch('/api/v1/articles/stats')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setSourceStats(data?.sources ?? null))
      .catch(() => setSourceStats(null));
    void fetchTasks();
    // TikHub 状态属于展示性信息，查询失败时静默降级
    void requestJson<Account>('/api/v1/tikhub/account')
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setAccountLoading(false));
  }, [fetchArticles, fetchTasks]);

  const completedCount = tasks.filter((task) => task.status === 'completed').length;
  const processingCount = tasks.filter((task) => task.status === 'processing' || task.status === 'pending').length;

  return (
    <div className="ac-stack">
      <section className="ac-kpis" aria-label="数据概览">
        <div className="ac-kpi">
          <div className="ac-kpi-label"><span className="ac-kpi-icon"><FileText size={14} /></span>文章总数</div>
          <div className="ac-kpi-value">{Math.max(articlesTotal, articles.length)}<small>篇</small></div>
          <div className="ac-kpi-hint">已进入前台文章库</div>
        </div>
        <div className="ac-kpi">
          <div className="ac-kpi-label"><span className="ac-kpi-icon"><CheckCircle2 size={14} /></span>已完成任务</div>
          <div className="ac-kpi-value">{completedCount}<small>条</small></div>
          <div className="ac-kpi-hint">抓取并保存成功</div>
        </div>
        <div className="ac-kpi">
          <div className="ac-kpi-label"><span className="ac-kpi-icon"><ListChecks size={14} /></span>处理中</div>
          <div className="ac-kpi-value">{processingCount}<small>{processingCount ? '进行中' : '空闲'}</small></div>
          <div className="ac-kpi-hint"><Link className="ac-link" to="/admin/tasks">查看处理任务</Link></div>
        </div>
        <div className="ac-kpi">
          <div className="ac-kpi-label"><span className="ac-kpi-icon"><Wallet size={14} /></span>TikHub 余额</div>
          {accountLoading ? (
            <>
              <div className="ac-kpi-value is-empty">—</div>
              <div className="ac-kpi-hint">正在查询账户…</div>
            </>
          ) : account === null ? (
            <>
              <div className="ac-kpi-value is-empty">—</div>
              <div className="ac-kpi-hint">账户信息暂不可用</div>
            </>
          ) : !account.configured ? (
            <>
              <div className="ac-kpi-value is-empty">未配置</div>
              <div className="ac-kpi-hint"><Link className="ac-link" to="/admin/tikhub"><Settings2 size={13} /> 前往配置 Key</Link></div>
            </>
          ) : (
            <>
              <div className="ac-kpi-value">{money(account.user?.balance)}</div>
              <div className="ac-kpi-hint">今日请求 {account.daily_usage?.total_request_per_day ?? '—'} 次</div>
            </>
          )}
        </div>
      </section>

      <section className="ac-dash-grid" aria-label="内容数据图表">
        <ArticleTrendChart articles={articles} articlesTotal={Math.max(articlesTotal, articles.length)} />
        <SourceBreakdown articles={articles} sourceStats={sourceStats} />
        <div className="ac-card ac-span-2">
          <div className="ac-card-head">
            <h2 className="ac-card-title"><Newspaper size={15} /> 最近文章</h2>
            <div className="ac-card-head-actions">
              <Link className="ac-btn ghost sm" to="/admin/articles">全部文章</Link>
            </div>
          </div>
          <div className="ac-table-wrap">
            <table className="ac-table">
              <thead>
                <tr><th>文章</th><th>来源</th><th>保存时间</th></tr>
              </thead>
              <tbody>
                {articles.length === 0 ? (
                  <tr><td colSpan={3}><div className="ac-empty">还没有保存文章。回到前台提交一条链接即可开始。</div></td></tr>
                ) : articles.slice(0, 5).map((article) => (
                  <tr key={article.id}>
                    <td><Link className="cell-main" to={`/article/${article.id}`}>{article.title}</Link></td>
                    <td>{sourceLabels[article.source_type]}</td>
                    <td className="cell-time">{formatDistanceToNow(new Date(article.created_at))}前</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <TaskStatusChart tasks={tasks} />
      </section>
    </div>
  );
}
