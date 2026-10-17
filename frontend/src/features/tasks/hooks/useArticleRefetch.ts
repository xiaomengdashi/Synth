import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../../app/store/useAppStore';
import type { Article } from '../../articles/types';
import type { Task } from '../types';
import { summarizeTaskStep } from '../taskPresentation';
import { adminFetch } from '../../../utils/adminAuth';

type RefetchResponse = Task & { task_id: string };
type TaskResult = Task & { article?: Article; error?: string };

async function request<T>(url: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = window.setTimeout(abort, 20000);
  try {
    const response = await adminFetch(url, { ...init, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败（HTTP ${response.status}）`);
    return data as T;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export default function useArticleRefetch() {
  const { addTask, updateTask, updateArticle, pushToast } = useAppStore();
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const [revision, setRevision] = useState(0);
  const tracked = useRef(new Map<string, string>());
  const starting = useRef(new Set<string>());
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    let timer: number | undefined;
    const finish = (articleId: string) => {
      tracked.current.delete(articleId);
      setJobs(previous => {
        const next = { ...previous };
        delete next[articleId];
        return next;
      });
    };
    const poll = async () => {
      await Promise.all([...tracked.current].map(async ([articleId, taskId]) => {
        try {
          const task = await request<TaskResult>(`/api/v1/tasks/${encodeURIComponent(taskId)}/status`, {}, controller.signal);
          if (controller.signal.aborted) return;
          if (task.error) {
            finish(articleId);
            pushToast({ title: '任务记录已不存在，请刷新文章列表后重试。', tone: 'error' });
            return;
          }
          updateTask(taskId, task);
          if (task.status === 'completed') {
            const article = task.article ?? await request<Article>(`/api/v1/articles/${encodeURIComponent(articleId)}`, {}, controller.signal);
            if (controller.signal.aborted) return;
            updateArticle(articleId, article);
            useAppStore.setState(state => ({ statsVersion: state.statsVersion + 1 }));
            setRevision(value => value + 1);
            finish(articleId);
            pushToast({ title: '文章已重新获取，正文和摘要已更新。', tone: 'success' });
          } else if (task.status === 'failed') {
            finish(articleId);
            pushToast({ title: `${summarizeTaskStep(task.current_step || '重新获取失败')}；原内容未替换`, tone: 'error' });
          } else {
            const step = summarizeTaskStep(task.current_step || '正在重新获取…');
            setJobs(previous => previous[articleId] === step ? previous : { ...previous, [articleId]: step });
          }
        } catch {
          if (!controller.signal.aborted) setJobs(previous => ({ ...previous, [articleId]: '进度暂不可用，正在重新连接…' }));
        }
      }));
      if (!controller.signal.aborted) timer = window.setTimeout(() => void poll(), 2000);
    };
    const resume = async () => {
      try {
        const result = await request<{ data: Task[] }>('/api/v1/tasks', {}, controller.signal);
        if (controller.signal.aborted) return;
        for (const task of result.data) {
          if (!task.article_id || !['pending', 'processing'].includes(task.status) || tracked.current.has(task.article_id)) continue;
          tracked.current.set(task.article_id, task.id);
          setJobs(previous => ({ ...previous, [task.article_id!]: summarizeTaskStep(task.current_step || '正在重新获取…') }));
        }
      } catch { /* A new submission still works if existing-task discovery fails. */ }
      if (!controller.signal.aborted) void poll();
    };
    void resume();
    return () => {
      mounted.current = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [pushToast, updateArticle, updateTask]);

  const refetchArticle = async (article: Article) => {
    if (starting.current.has(article.id) || tracked.current.has(article.id)) return;
    starting.current.add(article.id);
    setJobs(previous => ({ ...previous, [article.id]: '正在提交重新获取任务…' }));
    try {
      const task = await request<RefetchResponse>(`/api/v1/articles/${encodeURIComponent(article.id)}/refetch`, { method: 'POST' });
      if (!mounted.current) return;
      tracked.current.set(article.id, task.task_id);
      const record = { ...task, id: task.task_id };
      if (useAppStore.getState().tasks.some(item => item.id === record.id)) updateTask(record.id, record);
      else addTask(record);
      setJobs(previous => ({ ...previous, [article.id]: task.current_step || '等待重新获取' }));
      pushToast({ title: '已开始重新获取，可在处理任务中查看进度。', tone: 'success' });
    } catch (error) {
      if (mounted.current) {
        setJobs(previous => {
          const next = { ...previous };
          delete next[article.id];
          return next;
        });
        pushToast({ title: `启动失败：${error instanceof Error ? error.message : '请稍后重试'}`, tone: 'error' });
      }
    } finally {
      starting.current.delete(article.id);
    }
  };

  return { jobs, revision, refetchArticle };
}
