import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, BookOpen, Loader2, RefreshCw, X } from 'lucide-react';
import type { Article } from '../../articles/types';
import { sourceLabel } from '../../articles/components/ArticleList';
import { formatAbsolute } from '../../../utils/formatDate';

export default function ArticleInspector({ article, categories, onClose, onCategory, onRefetch, refetchStep }: {
  article: Article | null; categories: string[]; onClose: () => void; onCategory: (article: Article, category: string) => void;
  onRefetch: (article: Article) => void; refetchStep?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<Article | null>(null);
  const [failed, setFailed] = useState(false);
  const articleId = article?.id;
  useEffect(() => {
    const node = dialog.current;
    if (article && !node?.open) node?.showModal();
    if (!article && node?.open) node.close();
  }, [article]);
  useEffect(() => {
    if (!articleId) return;
    let cancelled = false;
    setDetail(null); setFailed(false);
    fetch(`/api/v1/articles/${articleId}`).then(res => { if (!res.ok) throw new Error(); return res.json(); })
      .then(data => { if (!cancelled) setDetail(data); }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [articleId]);
  return <dialog ref={dialog} className="article-inspector" aria-labelledby="inspector-title" onCancel={onClose} onClose={onClose} onClick={event => { if (event.target === dialog.current) { const rect = dialog.current.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}>
    {article && <><header><span>文章详情</span><button className="ac-icon-btn" aria-label="关闭文章详情" onClick={onClose} autoFocus><X size={18} /></button></header>
      <div className="inspector-body"><span className="ac-badge">{sourceLabel(article.source_type)}</span><h2 id="inspector-title">{article.title}</h2>
        <p className="inspector-summary">{article.summary || detail?.summary || '暂无摘要，打开文章阅读完整内容。'}</p>
        <dl><div><dt>保存时间</dt><dd>{formatAbsolute(new Date(article.created_at))}</dd></div><div><dt>阅读状态</dt><dd>{article.read_progress >= 0.95 ? '已读' : article.read_progress > 0 ? `已读 ${Math.round(article.read_progress * 100)}%` : '未读'}</dd></div></dl>
        <div className="ac-field"><label htmlFor="inspector-category">文章分类</label><select id="inspector-category" className="ac-select" value={article.category || ''} onChange={event => onCategory(article, event.target.value)}><option value="">未分类</option>{categories.map(name => <option key={name}>{name}</option>)}</select></div>
        {failed && <p className="ac-help">原文信息暂时无法加载，可打开文章重试。</p>}
        {refetchStep && <p className="ac-help article-refetch-progress" role="status">{refetchStep}</p>}
      </div><footer><Link className="ac-btn primary" to={`/article/${article.id}`}><BookOpen size={15} />打开阅读</Link><button className="ac-btn secondary" type="button" disabled={Boolean(refetchStep)} onClick={() => onRefetch(article)} title="根据原始链接更新正文和摘要，失败保留原内容">{refetchStep ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}{refetchStep ? '获取中' : '重新获取'}</button>{detail?.original_url && <a className="ac-btn secondary" href={detail.original_url} target="_blank" rel="noopener noreferrer">查看原文<ArrowUpRight size={15} /></a>}</footer></>}
  </dialog>;
}
