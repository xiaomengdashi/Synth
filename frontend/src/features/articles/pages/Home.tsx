import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, FileText, Link2, Loader2, Send, Twitter, Upload, Video, X } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '../../app/store/useAppStore';
import type { Article } from '../types';
import type { Task } from '../../tasks/types';
import { formatDistanceToNow } from '../../../utils/formatDate';
import ArticleList from '../components/ArticleList';

type Source = 'wechat' | 'x' | 'bilibili';
type TaskStatusResponse = {
  status?: Task['status'];
  current_step?: string;
  article_id?: string;
  article?: Article;
  error?: string;
};

const sourceMeta: Record<Source, { label: string; icon: typeof FileText; placeholder: string }> = {
  wechat: { label: '微信公众号', icon: FileText, placeholder: '粘贴 mp.weixin.qq.com 文章链接' },
  x: { label: 'X / Twitter', icon: Twitter, placeholder: '粘贴 x.com 文章或帖子链接' },
  bilibili: { label: 'Bilibili', icon: Video, placeholder: '粘贴 bilibili.com 视频链接' },
};

function detectSourceFromUrl(value: string): Source | null {
  try {
    const hostname = new URL(value.trim()).hostname.toLowerCase();
    if (hostname === 'mp.weixin.qq.com' || hostname.endsWith('.weixin.qq.com')) return 'wechat';
    if (hostname === 'x.com' || hostname.endsWith('.x.com') || hostname === 'twitter.com' || hostname.endsWith('.twitter.com')) return 'x';
    if (hostname === 'bilibili.com' || hostname.endsWith('.bilibili.com') || hostname === 'b23.tv') return 'bilibili';
  } catch {
    // Keep the current selection while the user is still typing a URL.
  }
  return null;
}

export default function Home() {
  const { articles, config, addTask, updateTask, addArticle, fetchArticles, pushToast } = useAppStore();
  const [source, setSource] = useState<Source>('wechat');
  const [url, setUrl] = useState('');
  const [detectedSource, setDetectedSource] = useState<Source | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [htmlImportOpen, setHtmlImportOpen] = useState(false);
  const [htmlOriginalUrl, setHtmlOriginalUrl] = useState('');
  const [htmlText, setHtmlText] = useState('');
  const [htmlFileName, setHtmlFileName] = useState('');
  const [isHtmlImporting, setIsHtmlImporting] = useState(false);

  const pollTaskStatus = async (backendTaskId: string, localTaskId: string) => {
    let pollCount = 0;
    while (pollCount < 120) {
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
            pushToast({ title: '内容已保存，已加入前台文章库', tone: 'success' });
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
    setIsSubmitting(true);
    const originalUrl = url.trim();
    const localTaskId = Math.random().toString(36).slice(2, 11);
    addTask({
      id: localTaskId,
      original_url: originalUrl,
      status: 'pending',
      current_step: '正在提交链接…',
      created_at: new Date().toISOString(),
    });
    setUrl('');
    setDetectedSource(null);

    try {
      const response = await fetch('/api/v1/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: originalUrl,
          config: {
            biliSessdata: config.biliSessdata,
            biliJct: config.biliJct,
            biliBuvid3: config.biliBuvid3,
          },
        }),
      });
      if (!response.ok) throw new Error('提交任务失败');
      const data = await response.json();
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
      const response = await fetch('/api/v1/articles/import-html', {
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
    <div>
      <section className="public-hero">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .55 }}>
          <div className="eyebrow">Personal intelligence desk / 01</div>
          <h1 className="display-title">把散落在网上的<br /><em>好内容，收回来。</em></h1>
          <p className="lede">导入微信公众号、X 或 Bilibili 内容；遇到微信安全验证时，也可以直接导入保存的网页 HTML。</p>
        </motion.div>
        <motion.div className="hero-note" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: .2, duration: .55 }}>
          <strong>一条链接，进入你的知识库</strong>
          <p>普通链接会自动整理；受保护的微信文章可通过网页 HTML 导入，内容完成后直接进入文章库。</p>
          <span className="mono-line"><i /> pipeline ready · waiting for input</span>
        </motion.div>
      </section>

      <motion.section className="import-strip" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .15, duration: .45 }}>
        <div className="import-topline">
          <h2>导入一条内容</h2>
          <div className="import-topline-actions">
            <span>WECHAT · X · BILIBILI</span>
            <button type="button" className="secondary-button" onClick={() => setHtmlImportOpen(true)}><Upload size={14} />导入网页 HTML</button>
          </div>
        </div>
        <form className="import-form" onSubmit={handleSubmit}>
          <label className="source-select">
            <span>{(() => { const Icon = sourceMeta[source].icon; return <Icon size={15} />; })()}</span>
            <select value={source} onChange={(event) => setSource(event.target.value as Source)} aria-label="选择来源">
              {Object.entries(sourceMeta).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
            </select>
          </label>
          <label className="import-input-wrap">
            <Link2 size={16} />
            <input
              value={url}
              onChange={(event) => {
                const nextUrl = event.target.value;
                const detected = detectSourceFromUrl(nextUrl);
                setUrl(nextUrl);
                setDetectedSource(detected);
                if (detected) setSource(detected);
              }}
              placeholder={sourceMeta[source].placeholder}
              type="url"
              required
            />
          </label>
          <button type="submit" className="primary-button" disabled={isSubmitting || !url.trim()}>
            {isSubmitting ? <><Loader2 size={15} className="animate-spin" />处理中</> : <><Send size={15} />开始整理</>}
          </button>
        </form>
        <div className="import-hint">
          {detectedSource ? <Check size={13} /> : <Link2 size={13} />}
          {detectedSource ? `已自动识别为 ${sourceMeta[detectedSource].label}` : '粘贴链接后会自动识别来源类型；微信安全验证不会自动打开浏览器。'}
        </div>
      </motion.section>

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
                  <textarea id="html-source" className="html-source-input" value={htmlText} onChange={(event) => setHtmlText(event.target.value)} placeholder="将保存的网页 HTML 粘贴到这里，需包含微信公众号的 #js_content 正文节点。" rows={10} required />
                </div>
              </div>
              <div className="modal-footer"><button type="button" className="secondary-button" onClick={() => setHtmlImportOpen(false)} disabled={isHtmlImporting}>取消</button><button type="submit" className="primary-button" disabled={isHtmlImporting || !htmlOriginalUrl.trim() || !htmlText.trim()}>{isHtmlImporting ? <><Loader2 size={14} className="animate-spin" />导入中</> : <><Upload size={14} />导入文章</>}</button></div>
            </form>
          </section>
        </div>
      ) : null}

      <section id="latest-articles" className="article-section">
        <div className="section-heading">
          <div><div className="eyebrow">Library / 02</div><h2>最近整理</h2><p>按生成时间排序，最新内容会出现在最前面。</p></div>
          <span className="text-link">{articles.length} 篇文章 <ArrowRight size={14} /></span>
        </div>
        <ArticleList articles={articles.slice(0, 6)} />
        {articles.length > 6 ? <Link className="text-link" to="/articles">查看全部文章 <ArrowRight size={14} /></Link> : null}
      </section>
    </div>
  );
}
