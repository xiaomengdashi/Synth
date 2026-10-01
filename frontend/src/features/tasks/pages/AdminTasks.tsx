import { useEffect, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import type { Task } from '../types';
import AdminPageHeader from '../components/AdminPageHeader';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { formatDistanceToNow } from '../../../utils/formatDate';

const STATUS_BADGES: Record<Task['status'], { cls: string; label: string }> = {
  completed: { cls: 'success', label: '已完成' },
  processing: { cls: 'processing', label: '处理中' },
  pending: { cls: 'pending', label: '排队中' },
  failed: { cls: 'danger', label: '失败' },
};

export default function AdminTasks() {
  const { tasks, fetchTasks, deleteArticle } = useAppStore();
  const [pendingDelete, setPendingDelete] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState(false);

  // 任务由后台异步推进,定时轮询让列表自动跟进状态
  useEffect(() => {
    void fetchTasks();
    const timer = window.setInterval(() => { void fetchTasks(); }, 5000);
    return () => window.clearInterval(timer);
  }, [fetchTasks]);

  return (
    <div>
      <AdminPageHeader
        summary={<><span>共 {tasks.length} 条任务记录</span><span>· 每 5 秒自动刷新</span></>}
        actions={<button type="button" className="ac-btn secondary sm" onClick={() => void fetchTasks()}><RefreshCw size={13} />立即刷新</button>}
      />
      <section className="ac-card">
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>链接</th>
                <th>状态</th>
                <th>提交时间</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr><td colSpan={4}><div className="ac-empty">当前没有处理任务。回到前台提交一条链接即可开始。</div></td></tr>
              ) : tasks.map((task) => {
                const badge = STATUS_BADGES[task.status];
                const step = task.status === 'completed' ? '' : task.current_step;
                return (
                  <tr key={task.id}>
                    <td>
                      <span className="cell-main" title={task.original_url}>{task.original_url}</span>
                      {step ? <span className="cell-sub">{step}</span> : null}
                    </td>
                    <td><span className={`ac-badge ${badge.cls}`}>{badge.label}</span></td>
                    <td className="cell-time">{formatDistanceToNow(new Date(task.created_at))}</td>
                    <td>
                      {task.status === 'completed' && task.article_id ? (
                        <div className="ac-row-actions">
                          <Link className="ac-btn secondary sm" to={`/article/${task.article_id}`}>查看文章</Link>
                          <button className="ac-btn danger-ghost sm icon" type="button" onClick={() => setPendingDelete(task)} aria-label="删除文章"><Trash2 size={13} /></button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这篇文章？"
        description="该任务对应的文章将被永久删除，不可恢复。"
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (!pendingDelete?.article_id) return;
          setDeleting(true);
          void deleteArticle(pendingDelete.article_id).then(() => {
            setDeleting(false);
            setPendingDelete(null);
          });
        }}
      />
    </div>
  );
}
