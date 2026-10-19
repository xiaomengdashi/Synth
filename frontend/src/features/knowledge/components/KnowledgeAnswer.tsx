import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ExternalLink, FileText } from 'lucide-react';
import { remarkKnowledgeCitations, sourceAnchorId } from '../lib/citations';
import type { KnowledgeTurn } from '../types';

export default function KnowledgeAnswer({turn}: {turn: KnowledgeTurn}) {
  return <div className="knowledge-answer">
    <div className="knowledge-markdown">
      <ReactMarkdown skipHtml remarkPlugins={[remarkGfm, [remarkKnowledgeCitations, {turnId:turn.id,numbers:turn.sources.map(s => s.number)}]]}
        components={{h1({children}) {return <h3>{children}</h3>;}, h2({children}) {return <h3>{children}</h3>;}, a({href, children}) {
          if (href?.startsWith('#knowledge-source-')) return <a href={href} className="knowledge-citation" aria-label={`查看引用 ${String(children)}`} onClick={event => {
            event.preventDefault();
            const target = document.getElementById(href.slice(1));
            if (target instanceof HTMLDetailsElement) target.open = true;
            target?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'nearest'});
            target?.focus({preventScroll:true});
          }}>{children}</a>;
          return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
        }, img() { return null; }}}>{turn.answer}</ReactMarkdown>
    </div>
    {turn.sources.length > 0 && <div className="knowledge-sources" aria-label="回答引用资料">
      <div className="knowledge-sources-label"><FileText size={13} />参考资料 · {turn.sources.length} 段</div>
      {turn.sources.map(source => <details className="knowledge-source" key={source.number} id={sourceAnchorId(turn.id,source.number)} tabIndex={-1}>
        <summary><span className="knowledge-source-number">{source.number}</span><span>{source.title}</span><span className="knowledge-source-expand">查看片段</span></summary>
        <div className="knowledge-source-content">
          <blockquote>{source.excerpt}</blockquote>
          {source.article_exists ? <a href={`/article/${encodeURIComponent(source.article_id)}`} target="_blank" rel="noopener noreferrer">打开文章 <ExternalLink size={12}/></a> : <span className="knowledge-muted">原文章已删除 · 保留当时引用片段</span>}
        </div>
      </details>)}
    </div>}
  </div>;
}
