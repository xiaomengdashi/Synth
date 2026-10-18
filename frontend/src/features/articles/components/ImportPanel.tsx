import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Clipboard, Link2, Loader2, Send, Smartphone, Upload, X } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { adminFetch } from '../../../utils/adminAuth';
import type { Article } from '../types';
import type { Task } from '../../tasks/types';

import { SOURCE_META as sourceMeta, detectSourceFromUrl, normalizeContentUrl, type Source } from '../lib/contentSources';
type TaskStatusResponse = {
  status?: Task['status'];
  current_step?: string;
  article_id?: string;
  article?: Article;
  error?: string;
};

export default function ImportPanel() {
  const { addTask, updateTask, addArticle, fetchArticles, pushToast } = useAppStore();
  const [source, setSource] = useState<Source>('wechat');
  const [url, setUrl] = useState('');
  const [detectedSource, setDetectedSource] = useState<Source | null>(null);
  const [clipboardMessage, setClipboardMessage] = useState('');
  const [isPasting, setIsPasting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [htmlImportOpen, setHtmlImportOpen] = useState(false);
  const [htmlOriginalUrl, setHtmlOriginalUrl] = useState('');
  const [htmlText, setHtmlText] = useState('');
  const [htmlFileName, setHtmlFileName] = useState('');
  const [isHtmlImporting, setIsHtmlImporting] = useState(false);

  const pollTaskStatus = async (backendTaskId: string, localTaskId: string) => {
    let pollCount = 0;
    while (pollCount < 600) {
      try {
        const response = await fetch(`/api/v1/tasks/${backendTaskId}/status`);
        const data: TaskStatusResponse = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || '获取任务状态失败');
        updateTask(localTaskId, {
          status: data.status || 'failed',
          current_step: data.current_step || '任务状态异常',
          article_id: data.article_id,
        });
        if (data.status === 'completed' || data.status === 'failed') {
          setIsSubmitting(false);
          if (data.status === 'completed') {
            if (data.article) addArticle(data.article);
            await fetchArticles();
            pushToast({ title: '内容已保存，已加入文章库', tone: 'success' });
          } else {
            pushToast({ title: data.current_step || '处理失败，请检查配置', tone: 'error' });
          }
          return;
        }
      } catch (error) {
        console.error('Polling error:', error);
      }
      pollCount += 1;
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    updateTask(localTaskId, { status: 'failed', current_step: '任务处理超时' });
    setIsSubmitting(false);
    pushToast({ title: '任务处理超时，请到后台查看', tone: 'error' });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    const normalizedUrl = normalizeContentUrl(url);
    if (!normalizedUrl) {
      pushToast({ title: '链接格式看不懂，请检查后重新粘贴', tone: 'error' });
      return;
    }
    setIsSubmitting(true);
    const originalUrl = normalizedUrl;
    const localTaskId = Math.random().toString(36).slice(2, 11);
    addTask({
      id: localTaskId,
      original_url: originalUrl,
      status: 'pending',
      current_step: '正在提交链接…',
      created_at: new Date().toISOString(),
    });

    try {
      const response = await fetch('/api/v1/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: originalUrl }),
      });
      if (!response.ok) throw new Error('提交任务失败');
      const data = await response.json();
      setUrl('');
      setDetectedSource(null);
      updateTask(localTaskId, { status: 'processing', current_step: '已进入处理队列' });
      void pollTaskStatus(data.task_id, localTaskId);
    } catch (error) {
      updateTask(localTaskId, {
        status: 'failed',
        current_step: `提交失败：${error instanceof Error ? error.message : '未知错误'}`,
      });
      setIsSubmitting(false);
      pushToast({ title: '链接提交失败，请稍后重试', tone: 'error' });
    }
  };

  const applyUrlInput = (nextUrl: string) => {
    const detected = detectSourceFromUrl(nextUrl);
    setUrl(nextUrl);
    setDetectedSource(detected);
    if (detected) setSource(detected);
  };

  const handlePasteImport = async () => {
    if (!navigator.clipboard?.readText) {
      setClipboardMessage('当前浏览器不支持直接读取剪贴板，请手动粘贴。');
      return;
    }
    setIsPasting(true);
    setClipboardMessage('');
    try {
      const clipboardText = (await navigator.clipboard.readText()).trim();
      if (!clipboardText) {
        setClipboardMessage('剪贴板里还没有可导入的内容。');
        return;
      }
      applyUrlInput(clipboardText);
    } catch {
      setClipboardMessage('没有拿到剪贴板权限，请先允许访问，或手动粘贴。');
    } finally {
      setIsPasting(false);
    }
  };

  const handleHtmlFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) {
      pushToast({ title: 'HTML 文件不能超过 15 MB', tone: 'error' });
      return;
    }
    setHtmlFileName(file.name);
    setHtmlText(await file.text());
  };

  const handleHtmlImport = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!htmlOriginalUrl.trim() || !htmlText.trim()) return;
    setIsHtmlImporting(true);
    try {
      const response = await adminFetch('/api/v1/articles/import-html', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original_url: htmlOriginalUrl.trim(), html: htmlText }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'HTML 导入失败');
      addArticle(data);
      await fetchArticles();
      setHtmlImportOpen(false);
      setHtmlOriginalUrl('');
      setHtmlText('');
      setHtmlFileName('');
      pushToast({ title: '网页 HTML 已导入文章库', tone: 'success' });
    } catch (error) {
      pushToast({ title: error instanceof Error ? error.message : 'HTML 导入失败', tone: 'error' });
    } finally {
      setIsHtmlImporting(false);
    }
  };

  return (
    <>
      <section className="collect-shell compact-collect">
        <form className="collect-bar" onSubmit={handleSubmit}>
          <select className="collect-source-select" aria-label="选择来源" value={source} onChange={event => setSource(event.target.value as Source)}>
            {(Object.keys(sourceMeta) as Source[]).map(value => <option key={value} value={value}>{sourceMeta[value].label}</option>)}
          </select>
          <label className="collect-input-wrap">
            <Link2 size={16} aria-hidden="true" />
            <input
              value={url}
              onChange={(event) => {
                applyUrlInput(event.target.value);
                setClipboardMessage('');
              }}
              placeholder={sourceMeta[source].placeholder}
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              aria-label="粘贴内容链接"
            />
          </label>
          <button type="button" className="import-paste-button" onClick={() => void handlePasteImport()} disabled={isSubmitting || isPasting} aria-label="读取剪贴板并填入" title="读取剪贴板并填入">
            {isPasting ? <Loader2 size={15} className="animate-spin" /> : <Clipboard size={15} />}
          </button>
          <button type="submit" className="primary-button" disabled={isSubmitting || !url.trim()}>
            {isSubmitting ? <><Loader2 size={15} className="animate-spin" />处理中</> : <><Send size={15} />开始导入</>}
          </button>
        </form>
        <p className="collect-hint">
          {detectedSource ? <Check size={13} /> : <Link2 size={13} />}
          {clipboardMessage || (detectedSource ? `已自动识别为 ${sourceMeta[detectedSource].label}` : '粘贴文章或视频链接，自动识别来源。')}
        </p>
        <div className="collect-alt">
          <Link to="/admin/share"><Smartphone size={13} />iPhone 分享导入</Link>
          <button type="button" onClick={() => setHtmlImportOpen(true)}><Upload size={13} />导入网页 HTML</button>
        </div>
      </section>

      {htmlImportOpen ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !isHtmlImporting && setHtmlImportOpen(false)}>
          <section className="config-modal html-import-modal" role="dialog" aria-modal="true" aria-labelledby="html-import-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="config-modal-header">
              <div><h2 id="html-import-title">导入保存的网页 HTML</h2><p>不打开浏览器、不重新访问微信，直接导入你保存的完整网页。</p></div>
              <button type="button" className="modal-close" aria-label="关闭 HTML 导入" onClick={() => setHtmlImportOpen(false)} disabled={isHtmlImporting}><X size={17} /></button>
            </div>
            <form onSubmit={handleHtmlImport}>
              <div className="form-grid">
                <div className="form-field full">
                  <label htmlFor="html-original-url">原文链接</label>
                  <input id="html-original-url" type="url" value={htmlOriginalUrl} onChange={(event) => setHtmlOriginalUrl(event.target.value)} placeholder="https://mp.weixin.qq.com/s/..." required />
                  <p className="form-help">请填写文章原始链接，用于标题、来源和文章归档。</p>
                </div>
                <div className="form-field full">
                  <label>网页文件</label>
                  <div className="html-file-row">
                    <label className="secondary-button html-file-button"><Upload size={14} />选择 HTML 文件<input type="file" accept=".html,.htm,text/html" onChange={handleHtmlFile} /></label>
                    <span>{htmlFileName || '也可以直接在下方粘贴源码'}</span>
                  </div>
                </div>
                <div className="form-field full">
                  <label htmlFor="html-source">网页源码</label>
                  <textarea id="html-source" className="html-source-input" value={htmlText} onChange={(event) => setHtmlText(event.target.value)} placeholder="粘贴保存的完整网页 HTML 源码。" rows={10} required />
                </div>
              </div>
              <div className="modal-footer"><button type="button" className="secondary-button" onClick={() => setHtmlImportOpen(false)} disabled={isHtmlImporting}>取消</button><button type="submit" className="primary-button" disabled={isHtmlImporting || !htmlOriginalUrl.trim() || !htmlText.trim()}>{isHtmlImporting ? <><Loader2 size={14} className="animate-spin" />导入中</> : <><Upload size={14} />导入文章</>}</button></div>
            </form>
          </section>
        </div>
      ) : null}

    </>
  );
}
