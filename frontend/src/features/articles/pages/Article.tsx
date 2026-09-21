import { useParams, Link, useNavigate } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import type { Article as ArticleType } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import hljs from 'highlight.js';
import 'highlight.js/styles/github-dark.css'; // 使用更经典美观的 GitHub Dark 主题
import { motion } from 'framer-motion';
import { ArrowLeft, ArrowUp, ExternalLink, Calendar, Link as LinkIcon, Loader2, Sparkles, Trash2 } from 'lucide-react';
import { useEffect, useState, useRef } from 'react';

const HTML_CONTENT_START = '<!-- HTML_CONTENT_START -->';
const HTML_CONTENT_END = '<!-- HTML_CONTENT_END -->';
const X_CONTENT_START = '<!-- X_CONTENT_START -->';
const X_CONTENT_END = '<!-- X_CONTENT_END -->';
const SUMMARY_SECTION_PATTERN = /^##\s*(?:(?:AI\s*)?摘要|内容摘要)\s*\n+([\s\S]*?)\n+\s*---\s*\n*/;

interface XPreviewData {
  author_name: string;
  author_handle?: string;
  author_avatar_url?: string;
  tweet_text: string;
  media_urls: string[];
  article_preview?: {
    title?: string;
    preview_text?: string;
    image?: string;
  } | null;
  likes?: number;
  retweets?: number;
  replies?: number;
  created_at?: string;
  tweet_url?: string;
}

interface ArticleHeading {
  id: string;
  text: string;
  level: number;
}

function ArticleToc({
  items,
  open,
  onToggle,
  onNavigate,
}: {
  items: ArticleHeading[];
  open: boolean;
  onToggle: () => void;
  onNavigate: () => void;
}) {
  return (
    <nav className={`article-toc ${open ? 'is-open' : ''}`} aria-label="文章目录">
      <button type="button" className="article-toc-toggle" onClick={onToggle} aria-expanded={open}>
        <span><span className="article-toc-kicker">Contents</span><strong>文章目录</strong></span>
        <span className="article-toc-count">{items.length} 节</span>
      </button>
      <ol className="article-toc-list">
        {items.map((item) => (
          <li key={item.id} className={`article-toc-level-${item.level}`}>
            <a href={`#${item.id}`} onClick={onNavigate}>{item.text}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function extractWechatSections(contentMd: string, fallbackSummary: string) {
  const htmlStartIndex = contentMd.indexOf(HTML_CONTENT_START);
  const markdownContent = htmlStartIndex >= 0 ? contentMd.slice(0, htmlStartIndex) : contentMd;
  const htmlContent = htmlStartIndex >= 0
    ? contentMd.slice(htmlStartIndex + HTML_CONTENT_START.length).replace(HTML_CONTENT_END, '').trim()
    : '';

  const summaryMatch = markdownContent.match(SUMMARY_SECTION_PATTERN);
  const summaryMarkdown = (summaryMatch?.[1] ?? fallbackSummary).trim();
  const bodyMarkdown = summaryMatch
    ? markdownContent.slice(summaryMatch[0].length).trim()
    : markdownContent.trim();

  return {
    summaryMarkdown,
    bodyMarkdown,
    htmlContent,
  };
}

function extractEmbeddedXPayload(contentMd: string): XPreviewData | null {
  const startIndex = contentMd.indexOf(X_CONTENT_START);
  if (startIndex < 0) {
    return null;
  }

  const endIndex = contentMd.indexOf(X_CONTENT_END, startIndex);
  if (endIndex < 0) {
    return null;
  }

  const rawPayload = contentMd
    .slice(startIndex + X_CONTENT_START.length, endIndex)
    .trim();

  try {
    return JSON.parse(rawPayload) as XPreviewData;
  } catch {
    // Rich X articles use the same marker for Markdown content and legacy JSON previews.
    return null;
  }
}

function extractXSections(contentMd: string, fallbackSummary: string) {
  const markerIndex = contentMd.indexOf(X_CONTENT_START);
  const markdownContent = markerIndex >= 0 ? contentMd.slice(0, markerIndex) : contentMd;
  const contentEndIndex = markerIndex >= 0 ? contentMd.indexOf(X_CONTENT_END, markerIndex) : -1;
  const embeddedContent = markerIndex >= 0
    ? contentMd.slice(markerIndex + X_CONTENT_START.length, contentEndIndex >= 0 ? contentEndIndex : contentMd.length).trim()
    : '';
  const summaryMatch = markdownContent.match(SUMMARY_SECTION_PATTERN);
  const summaryMarkdown = (summaryMatch?.[1] ?? fallbackSummary).trim();
  const summaryBodyMarkdown = summaryMatch
    ? markdownContent.slice(summaryMatch[0].length).trim()
    : markdownContent.trim();

  let payload: XPreviewData | null = null;
  let articleMarkdown = '';
  if (embeddedContent) {
    try {
      payload = JSON.parse(embeddedContent) as XPreviewData;
    } catch {
      // X 长文正文也放在同一组标记中，但它是 Markdown 而不是 JSON。
      articleMarkdown = embeddedContent;
    }
  }

  return {
    summaryMarkdown,
    bodyMarkdown: articleMarkdown || summaryBodyMarkdown,
    payload,
  };
}

export default function Article() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const storeArticle = useAppStore((state) => state.articles.find((a) => a.id === id));
  const deleteArticle = useAppStore((state) => state.deleteArticle);
  
  const [article, setArticle] = useState<ArticleType | null>(storeArticle || null);
  const [loading, setLoading] = useState(!storeArticle);
  const [error, setError] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [xPreview, setXPreview] = useState<XPreviewData | null>(null);
  const [tocItems, setTocItems] = useState<ArticleHeading[]>([]);
  const [tocOpen, setTocOpen] = useState(false);
  const [showBackToTop, setShowBackToTop] = useState(false);

  const htmlContainerRef = useRef<HTMLDivElement>(null);
  const articleBodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleScroll = () => setShowBackToTop(window.scrollY > 520);
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    // 如果 store 中没有找到，说明可能是刷新了页面，尝试从后端拉取
    if (!storeArticle && id) {
      setLoading(true);
      fetch(`/api/v1/articles/${id}`)
        .then(res => {
          if (!res.ok) throw new Error('Article not found');
          return res.json();
        })
        .then(data => {
          // 因为后端返回的可能是单个对象，或者是 {data: [...]} 格式
          // 这里的单个文章接口返回的是单个对象
          setArticle(data);
          setLoading(false);
        })
        .catch(err => {
          console.error(err);
          setError(true);
          setLoading(false);
        });
    } else if (storeArticle) {
      setArticle(storeArticle);
    }
  }, [id, storeArticle]);

  // 仅对 CSDN 等无内联着色的代码块做 hljs；公众号正文已自带颜色，hljs 会破坏 <br/> 换行
  useEffect(() => {
    if (!article || !htmlContainerRef.current || article.source_type === 'wechat') {
      return;
    }

    const blocks = htmlContainerRef.current.querySelectorAll('pre code, .code-snippet, [class*="language-"]');
    blocks.forEach((block) => {
      const element = block as HTMLElement;
      if (element.closest('[data-wechat-code]')) {
        return;
      }
      hljs.highlightElement(element);
    });
  }, [article]);

  useEffect(() => {
    const body = articleBodyRef.current;
    if (!body) {
      setTocItems([]);
      return;
    }

    const seenIds = new Set<string>();
    const headings = Array.from(body.querySelectorAll('h1, h2, h3, h4, h5, h6'))
      .map((element, index) => {
        const text = (element.textContent || '').trim();
        if (!text) return null;

        const baseId = `article-section-${index + 1}`;
        let id = baseId;
        let suffix = 2;
        while (seenIds.has(id)) {
          id = `${baseId}-${suffix}`;
          suffix += 1;
        }
        seenIds.add(id);
        element.id = id;
        return { id, text, level: Number(element.tagName.slice(1)) };
      })
      .filter((item): item is ArticleHeading => item !== null);

    setTocItems(headings);
  }, [article]);

  useEffect(() => {
    if (!article || article.source_type !== 'x') {
      setXPreview(null);
      return;
    }

    const embeddedPayload = extractEmbeddedXPayload(article.content_md);
    if (embeddedPayload) {
      setXPreview(embeddedPayload);
      return;
    }

    fetch(`/api/v1/articles/x-preview?url=${encodeURIComponent(article.original_url)}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error('Failed to fetch tweet preview');
        }
        return res.json();
      })
      .then((data) => setXPreview(data))
      .catch((err) => {
        console.error(err);
        setXPreview(null);
      });
  }, [article]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
        <p className="text-slate-500">加载文章中...</p>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h2 className="text-2xl font-bold mb-4">文章未找到</h2>
        <Link to="/" className="text-primary hover:underline flex items-center gap-2">
          <ArrowLeft className="w-4 h-4" /> 返回首页
        </Link>
      </div>
    );
  }

  const wechatSections = article.source_type === 'wechat'
    ? extractWechatSections(article.content_md, article.summary)
    : null;
  const xSections = article.source_type === 'x'
    ? extractXSections(article.content_md, article.summary)
    : null;

  const markdownContent = xSections
    ? xSections.bodyMarkdown
    : wechatSections
    ? wechatSections.bodyMarkdown
    : article.content_md.includes(HTML_CONTENT_START)
      ? article.content_md.split(HTML_CONTENT_START)[0]
      : article.content_md;

  const htmlContent = wechatSections
    ? wechatSections.htmlContent
    : article.content_md.includes(HTML_CONTENT_START)
      ? article.content_md.split(HTML_CONTENT_START)[1].replace(HTML_CONTENT_END, '')
      : '';

  const xCreatedAt = xPreview?.created_at
    ? new Date(xPreview.created_at).toLocaleString('zh-CN', { hour12: false })
    : '';
  const isXArticle = article.source_type === 'x';

  const handleDelete = async () => {
    if (!article || isDeleting) {
      return;
    }

    setIsDeleting(true);
    const deleted = await deleteArticle(article.id);
    setIsDeleting(false);

    if (deleted) {
      navigate('/');
    }
  };

  return (
    <motion.article 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="max-w-4xl mx-auto"
    >
      <Link 
        to="/" 
        className="inline-flex items-center gap-2 text-slate-500 hover:text-primary transition-colors mb-8"
      >
        <ArrowLeft className="w-4 h-4" /> 返回首页
      </Link>

      <div className={isXArticle ? 'article-reader article-reader-x' : 'glass-panel rounded-3xl overflow-hidden shadow-xl'}>
        {isXArticle ? (
          <header className="x-article-header">
            <div className="x-article-kicker"><span>X Article</span><span>{new Date(article.created_at).toLocaleDateString('zh-CN')}</span></div>
            <h1>{article.title}</h1>
            <div className="x-article-byline">
              <img src={xPreview?.author_avatar_url || article.cover_image_url} alt={xPreview?.author_name || 'X 作者'} />
              <div>
                <strong>{xPreview?.author_name || 'X 作者'}</strong>
                <span>{xPreview?.author_handle ? `@${xPreview.author_handle}` : '来自 X 长文'}</span>
              </div>
              <a href={article.original_url} target="_blank" rel="noopener noreferrer">在 X 中打开 <ExternalLink size={13} /></a>
            </div>
            {xCreatedAt ? <p className="x-article-published">原文发布于 {xCreatedAt}</p> : null}
            {article.cover_image_url ? <img className="x-article-lead" src={article.cover_image_url} alt="X 文章封面" /> : null}
          </header>
        ) : (
          <div className="relative w-full h-64 sm:h-80 md:h-[400px] overflow-hidden">
            <img src={article.cover_image_url} alt={article.title} className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 via-slate-900/20 to-transparent" />
            <div className="absolute bottom-0 left-0 w-full p-6 md:p-10">
              <div className="flex items-center gap-4 text-white/80 text-sm font-medium mb-4">
                <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-md px-3 py-1 rounded-full"><Calendar className="w-4 h-4" />{new Date(article.created_at).toLocaleDateString('zh-CN')}</span>
                <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-md px-3 py-1 rounded-full"><LinkIcon className="w-4 h-4" />{article.source_type.toUpperCase()}</span>
              </div>
              <h1 className="text-3xl md:text-4xl lg:text-5xl font-extrabold text-white leading-tight">{article.title}</h1>
            </div>
          </div>
        )}

        {/* Content */}
        <div className={isXArticle ? 'x-article-content' : 'p-6 md:p-10 lg:p-12 bg-white dark:bg-slate-900'}>
          <div className="mb-8 flex flex-wrap justify-end gap-3">
            <button
              type="button"
              onClick={handleDelete}
              disabled={isDeleting}
              className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm font-medium text-red-600 transition-all hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20"
            >
              {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              {isDeleting ? '删除中...' : '删除文章'}
            </button>
            <a 
              href={article.original_url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-primary hover:text-white transition-all text-sm font-medium"
            >
              <ExternalLink className="w-4 h-4" /> 查看原文
            </a>
          </div>

          {wechatSections?.summaryMarkdown ? (
            <section className="relative mb-10 overflow-hidden rounded-[2rem] border border-emerald-200/80 bg-[linear-gradient(135deg,rgba(236,253,245,0.95),rgba(255,255,255,0.92),rgba(240,249,255,0.95))] p-6 shadow-[0_24px_60px_-32px_rgba(16,185,129,0.45)] dark:border-emerald-500/20 dark:bg-[linear-gradient(135deg,rgba(6,78,59,0.3),rgba(15,23,42,0.94),rgba(12,74,110,0.26))]">
              <div className="absolute -right-10 -top-10 h-36 w-36 rounded-full bg-emerald-300/20 blur-3xl dark:bg-emerald-400/10" />
              <div className="absolute bottom-0 left-0 h-28 w-28 rounded-full bg-sky-300/20 blur-3xl dark:bg-sky-400/10" />

              <div className="relative">
                <div className="inline-flex items-center gap-2 rounded-full border border-emerald-300/70 bg-white/80 px-4 py-2 text-sm font-semibold text-emerald-700 shadow-sm backdrop-blur dark:border-emerald-400/20 dark:bg-slate-900/60 dark:text-emerald-200">
                  <Sparkles className="h-4 w-4" />
                  微信文章内容导读
                </div>

                <div className="mt-5 space-y-4">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({ children }) => (
                        <p className="text-base leading-8 text-slate-700 dark:text-slate-200 md:text-[1.05rem]">
                          {children}
                        </p>
                      ),
                      ul: ({ children }) => (
                        <ul className="list-disc space-y-2 pl-5 text-slate-700 marker:text-emerald-500 dark:text-slate-200">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="list-decimal space-y-2 pl-5 text-slate-700 marker:font-semibold marker:text-emerald-600 dark:text-slate-200 dark:marker:text-emerald-300">
                          {children}
                        </ol>
                      ),
                      li: ({ children }) => (
                        <li className="pl-1 leading-7">
                          {children}
                        </li>
                      ),
                      strong: ({ children }) => (
                        <strong className="font-semibold text-slate-950 dark:text-white">
                          {children}
                        </strong>
                      ),
                      h1: ({ children }) => (
                        <h3 className="text-xl font-bold text-slate-950 dark:text-white">
                          {children}
                        </h3>
                      ),
                      h2: ({ children }) => (
                        <h3 className="text-xl font-bold text-slate-950 dark:text-white">
                          {children}
                        </h3>
                      ),
                      h3: ({ children }) => (
                        <h4 className="text-lg font-bold text-slate-950 dark:text-white">
                          {children}
                        </h4>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote className="border-l-4 border-emerald-400/70 bg-white/50 px-4 py-3 italic text-slate-700 dark:border-emerald-300/50 dark:bg-slate-900/40 dark:text-slate-200">
                          {children}
                        </blockquote>
                      ),
                    }}
                  >
                    {wechatSections.summaryMarkdown}
                  </ReactMarkdown>
                </div>
              </div>
            </section>
          ) : null}

          <div className={tocItems.length > 0 ? 'article-reading-layout' : ''}>
            {tocItems.length > 0 ? (
              <ArticleToc
                items={tocItems}
                open={tocOpen}
                onToggle={() => setTocOpen((current) => !current)}
                onNavigate={() => setTocOpen(false)}
              />
            ) : null}
            <div ref={articleBodyRef} className="article-body-content">
              {htmlContent ? (
                <>
                  {markdownContent.trim() ? (
                    <div className={`${isXArticle ? 'x-article-markdown' : ''} prose prose-slate dark:prose-invert max-w-none prose-img:mx-auto prose-img:rounded-xl prose-img:shadow-lg prose-img:block prose-headings:font-bold prose-a:text-primary hover:prose-a:text-blue-400 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800`}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                        {markdownContent}
                      </ReactMarkdown>
                    </div>
                  ) : null}
                  <div
                    ref={htmlContainerRef}
                    className={`article-html-container not-prose w-full ${markdownContent.trim() ? 'mt-8 border-t border-slate-200 pt-8 dark:border-slate-800' : ''}`}
                    dangerouslySetInnerHTML={{ __html: htmlContent }}
                  />
                </>
              ) : article.source_type === 'x' && xPreview && !markdownContent.trim() ? null : (
                <div className={`${isXArticle ? 'x-article-markdown' : ''} prose prose-slate dark:prose-invert max-w-none prose-img:mx-auto prose-img:rounded-xl prose-img:shadow-lg prose-img:block prose-headings:font-bold prose-a:text-primary hover:prose-a:text-blue-400 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800`}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {markdownContent}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      {showBackToTop ? (
        <button
          type="button"
          className="back-to-top"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          aria-label="一键回到顶部"
          title="一键回到顶部"
        >
          <ArrowUp size={16} />
          <span>回到顶部</span>
        </button>
      ) : null}
    </motion.article>
  );
}
