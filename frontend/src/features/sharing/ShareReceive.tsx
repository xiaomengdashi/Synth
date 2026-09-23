import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowRight, Check, Clipboard, Loader2, RotateCcw, Share2 } from 'lucide-react';
import { submitShare, watchSharedTask } from './shareClient';
import type { SharedTask } from './shareClient';

export default function ShareReceive() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const query = params.toString();
  const [task, setTask] = useState<SharedTask | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [manualUrl, setManualUrl] = useState('');
  const [manualMessage, setManualMessage] = useState('');
  const [pasting, setPasting] = useState(false);
  const hasInput = Boolean(params.get('task') || params.get('url') || params.get('text') || params.get('title'));

  useEffect(() => {
    const input = new URLSearchParams(query);
    if (!input.get('task') && !input.get('url') && !input.get('text') && !input.get('title')) return;
    const controller = new AbortController();
    setBusy(true);
    setNotice('');
    setTask(null);
    const complete = (result: SharedTask) => {
      if (result.status === 'completed' && result.article_id) {
        navigate(`/article/${encodeURIComponent(result.article_id)}`, { replace: true });
        return true;
      }
      return false;
    };
    void (async () => {
      try {
        const taskId = input.get('task');
        if (!taskId) {
          const result = await submitShare({ url: input.get('url') || '', text: input.get('text') || '', title: input.get('title') || '' });
          if (controller.signal.aborted) return;
          setTask(result);
          if (complete(result)) return;
          if (!result.task_id) throw new Error('服务器没有返回任务编号，请重新提交。');
          // The address now contains the durable task ID; refreshing resumes observation.
          setParams({ task: result.task_id }, { replace: true });
          return;
        }
        const result = await watchSharedTask(taskId, (next) => {
          if (!controller.signal.aborted) setTask(next);
        }, controller.signal);
        if (controller.signal.aborted || complete(result)) return;
        if (result.status !== 'failed') setNotice('文章仍在后台处理中。你可以稍后继续查看，或前往处理任务。');
      } catch (error) {
        if (!controller.signal.aborted) setNotice(error instanceof Error ? error.message : '导入失败，请重试。');
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, [query, attempt, navigate, setParams]);

  const retry = async () => {
    if (task?.status !== 'failed' || !task.original_url) {
      setAttempt((value) => value + 1);
      return;
    }
    setBusy(true);
    setNotice('');
    try {
      const result = await submitShare({ url: task.original_url, retry: true });
      if (result.article_id) navigate(`/article/${encodeURIComponent(result.article_id)}`, { replace: true });
      else if (result.task_id) {
        setParams({ task: result.task_id }, { replace: true });
        setAttempt((value) => value + 1);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '重试失败');
    } finally { setBusy(false); }
  };

  const startManualImport = (value: string) => {
    const nextValue = value.trim();
    if (!nextValue) return;
    setManualUrl(nextValue);
    setManualMessage('');
    setParams({ text: nextValue });
  };

  const pasteFromClipboard = async () => {
    if (!navigator.clipboard?.readText) {
      setManualMessage('当前浏览器不支持直接读取剪贴板，请手动粘贴。');
      return;
    }
    setPasting(true);
    setManualMessage('');
    try {
      const clipboardText = (await navigator.clipboard.readText()).trim();
      if (!clipboardText) {
        setManualMessage('剪贴板里还没有可导入的内容。');
        return;
      }
      startManualImport(clipboardText);
    } catch {
      setManualMessage('没有拿到剪贴板权限，请先允许访问，或手动粘贴。');
    } finally {
      setPasting(false);
    }
  };

  const failed = task?.status === 'failed';
  return (
    <div className="share-page">
      <div className="eyebrow">From your iPhone</div>
      <h1>把这篇好文章，收下来。</h1>
      <p className="share-lede">来自 X 或微信文章的分享，会自动整理并保存到你的文章库。</p>
      <section className="share-status-panel" aria-live="polite" aria-busy={busy}>
        <span className={`share-status-icon ${failed || notice ? 'has-notice' : ''}`}>
          {busy ? <Loader2 size={27} className="animate-spin" /> : failed || notice ? <AlertCircle size={27} /> : <Share2 size={27} />}
        </span>
        <h2>{failed ? '这次没有抓取成功' : notice ? '需要继续查看' : busy ? '正在保存这篇文章' : '等待一篇值得读的文章'}</h2>
        <p>{notice || task?.current_step || (hasInput ? '正在识别分享链接…' : '在 X 或微信文章中点击分享，选择「保存到 SynthAI」。也可以在下面粘贴链接。')}</p>
        {task?.original_url && <a className="share-source-url" href={task.original_url} target="_blank" rel="noreferrer">{task.original_url}</a>}
        {busy && <ol className="share-progress"><li><Check size={14} />接收分享</li><li><Loader2 size={14} className="animate-spin" />提取正文</li><li>保存文章</li></ol>}
        {!busy && hasInput && <button type="button" className="primary-button" onClick={() => void retry()}><RotateCcw size={15} />{failed ? '重新抓取' : '继续查看'}</button>}
        {!busy && (!hasInput || notice) && <form className="share-manual" onSubmit={(event) => { event.preventDefault(); startManualImport(manualUrl); }}>
          <label htmlFor="shared-url">X、微信文章或帖子链接</label>
          <input id="shared-url" type="url" placeholder="https://x.com/... 或 https://mp.weixin.qq.com/..." value={manualUrl} onChange={(event) => { setManualUrl(event.target.value); setManualMessage(''); }} required />
          <div className="share-manual-actions">
            <button type="button" className="secondary-button" onClick={() => void pasteFromClipboard()} disabled={pasting}>
              {pasting ? <Loader2 size={14} className="animate-spin" /> : <Clipboard size={14} />}
              {pasting ? '读取中' : '粘贴并导入'}
            </button>
            <button type="submit" className="secondary-button">导入文章 <ArrowRight size={14} /></button>
          </div>
          {manualMessage && <p className="share-inline-notice" role="status">{manualMessage}</p>}
        </form>}
      </section>
      <div className="share-footer-links"><Link to="/share/setup">设置 iPhone 分享入口</Link><Link to={hasInput ? '/admin/tasks' : '/articles'}>{hasInput ? '查看处理任务' : '打开文章库'} <ArrowRight size={14} /></Link></div>
    </div>
  );
}
