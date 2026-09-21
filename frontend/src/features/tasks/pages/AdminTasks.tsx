import { useEffect } from 'react';
import { Activity, AlertCircle, CheckCircle2, FileText, Loader2, Trash2, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '../../app/store/useAppStore';
import type { Task } from '../types';
import AdminPageHeader from '../components/AdminPageHeader';
import { formatDistanceToNow } from '../../../utils/formatDate';

function statusText(task: Task) {
  if (task.status === 'completed') return '已完成';
  if (task.status === 'failed') return '失败';
  if (task.status === 'processing') return task.current_step || '处理中';
  return '排队中';
}

export default function AdminTasks() {
  const { tasks, fetchTasks, deleteArticle } = useAppStore();
  useEffect(() => { void fetchTasks(); }, [fetchTasks]);

  return (
    <div>
      <AdminPageHeader eyebrow="Queue / 03" title="处理任务" description="独立查看每一条链接的抓取、总结和保存状态。" actions={<span className="text-link">实时更新 <Activity size={14} /></span>} />
      <section className="admin-section">
        <div className="task-list">
          <AnimatePresence initial={false}>
            {tasks.length === 0 ? <div className="empty-state">当前没有处理任务。请从前台提交一条链接。</div> : tasks.map((task) => (
              <motion.div className="task-row" key={task.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <div className="task-main">
                  <span className="task-icon">{task.status === 'processing' ? <Loader2 size={14} className="animate-spin" /> : task.status === 'completed' ? <CheckCircle2 size={14} /> : task.status === 'failed' ? <XCircle size={14} /> : <AlertCircle size={14} />}</span>
                  <div className="task-copy"><strong>{statusText(task)}</strong><span title={task.original_url}>{task.original_url}</span></div>
                </div>
                <span className={`task-status ${task.status === 'completed' ? 'done' : task.status === 'failed' ? 'failed' : ''}`}>{formatDistanceToNow(new Date(task.created_at))}前</span>
                {task.status === 'completed' && task.article_id ? <div className="task-actions"><Link className="tiny-button" to={`/article/${task.article_id}`}>查看文章</Link><button className="tiny-button" type="button" onClick={() => void deleteArticle(task.article_id!)}><Trash2 size={12} /></button></div> : null}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </section>
    </div>
  );
}
