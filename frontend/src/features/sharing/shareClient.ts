export interface SharedTask {
  task_id?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  current_step?: string;
  original_url?: string;
  article_id?: string;
  reused?: boolean;
}

export interface ShareInput { url?: string; text?: string; title?: string; retry?: boolean }

async function requestTask(url: string, init: RequestInit = {}, signal?: AbortSignal): Promise<SharedTask> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timeout = setTimeout(abort, 20000);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(typeof data.detail === 'string' ? data.detail : data.error || '提交失败，请检查链接后重试。');
    }
    if (!['pending', 'processing', 'completed', 'failed'].includes(data.status)) {
      throw new Error('服务器返回了无效的任务状态，请稍后重试。');
    }
    return data;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (controller.signal.aborted || error instanceof TypeError || error instanceof SyntaxError) {
      throw new Error('暂时连接不到 SynthAI，请确认电脑服务正在运行、手机网络可以访问，然后重试。');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abort);
  }
}

// Share pages can mount twice in StrictMode; the backend also deduplicates durably.
const submissions = new Map<string, Promise<SharedTask>>();
export function submitShare(input: ShareInput): Promise<SharedTask> {
  const body = JSON.stringify(input);
  const existing = submissions.get(body);
  if (existing) return existing;
  const request = requestTask('/api/v1/tasks/share', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
  }).finally(() => submissions.delete(body));
  submissions.set(body, request);
  return request;
}

function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  });
}

export async function watchSharedTask(
  taskId: string, onProgress: (task: SharedTask) => void, signal: AbortSignal,
  intervalMs = 2000, maxPolls = 180,
): Promise<SharedTask> {
  let task: SharedTask = { status: 'pending', task_id: taskId };
  for (let count = 0; count < maxPolls; count += 1) {
    task = await requestTask(`/api/v1/tasks/${encodeURIComponent(taskId)}/status`, {}, signal);
    onProgress(task);
    if (task.status === 'completed' || task.status === 'failed') return task;
    await pause(intervalMs, signal);
  }
  return task;
}
