import { useParams, Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import type { Article as ArticleType } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
// common 子集(~35 种常用语言)代替全量引入:全量会把详情页 chunk 撑到 1MB+,显著拖慢首屏
import hljs from 'highlight.js/lib/common';
import 'highlight.js/styles/github-dark.css'; // 使用更经典美观的 GitHub Dark 主题
import { motion } from 'framer-motion';
import { ArrowLeft, ArrowUp, ExternalLink, Loader2, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState, useRef } from 'react';
import WechatArticleView from '../components/WechatArticleView';
import type { WechatArticleViewHandle } from '../components/WechatArticleView';
import XArticleView from '../components/XArticleView';
import { extractXArticle } from '../lib/xArticle';
import { sourceColor, sourceLabel } from '../components/ArticleList';

const HTML_CONTENT_START = '<!-- HTML_CONTENT_START -->';
const HTML_CONTENT_END = '<!-- HTML_CONTENT_END -->';
const X_CONTENT_START = '<!-- X_CONTENT_START -->';
const X_CONTENT_END = '<!-- X_CONTENT_END -->';
const SUMMARY_SECTION_PATTERN = /^##\s*(?:(?:AI\s*)?摘要|内容摘要)\s*\n+([\s\S]*?)\n+\s*---\s*\n*/;

interface XMediaItem {
  type: 'photo' | 'video' | 'gif';
  url: string;
  poster?: string;
}

interface XPreviewData {
  author_name: string;
  author_handle?: string;
  author_avatar_url?: string;
  tweet_text: string;
  media_urls: string[];
  media_items?: XMediaItem[];
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
  activeId,
  onNavigate,
  preventDefaultJump,
}: {
  items: ArticleHeading[];
  activeId?: string;
  onNavigate: (item: ArticleHeading) => void;
  preventDefaultJump?: boolean;
}) {
  return (
    <nav className="article-toc" aria-label="文章目录">
      <div className="article-toc-head">
        <strong>目录</strong>
        <span className="article-toc-count">{items.length} 节</span>
      </div>
      <ol className="article-toc-list">
        {items.map((item) => (
          <li key={item.id} className={`article-toc-level-${item.level}`}>
            <a
              href={`#${item.id}`}
              title={item.text}
              className={item.id === activeId ? 'active' : undefined}
              onClick={(event) => {
                if (preventDefaultJump) event.preventDefault();
                onNavigate(item);
              }}
            >
              {item.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function extractWechatSections(contentMd: string, fallbackSummary: string) {
  if (!contentMd) {
    return { summaryMarkdown: fallbackSummary.trim(), bodyMarkdown: '', htmlContent: '' };
  }
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
  if (!contentMd) return null;
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
  if (!contentMd) {
    return { summaryMarkdown: fallbackSummary.trim(), bodyMarkdown: '', payload: null };
  }
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
  const storeArticle = useAppStore((state) => state.articles.find((a) => a.id === id));
  
  const [article, setArticle] = useState<ArticleType | null>(storeArticle || null);
  const [loading, setLoading] = useState(!storeArticle);
  const [error, setError] = useState(false);
  const [xPreview, setXPreview] = useState<XPreviewData | null>(null);
  const [tocItems, setTocItems] = useState<ArticleHeading[]>([]);
  const [activeTocId, setActiveTocId] = useState('');
  const [showBackToTop, setShowBackToTop] = useState(false);

  const htmlContainerRef = useRef<HTMLDivElement>(null);
  const articleBodyRef = useRef<HTMLDivElement>(null);
  const wechatViewRef = useRef<WechatArticleViewHandle>(null);

  const wechatSections = article?.source_type === 'wechat'
    ? extractWechatSections(article.content_md, article.summary)
    : null;
  const replicaHtmlContent = wechatSections?.htmlContent ?? '';
  const useWechatReplica = Boolean(wechatSections && replicaHtmlContent);
  // 必须记忆化：每次渲染返回新对象会让 XArticleView 的 srcDoc（含随机 nonce）不断变化，导致 iframe 无限重载闪烁
  const xArticleReplica = useMemo(
    () => (article?.source_type === 'x' ? extractXArticle(article.content_md) : null),
    [article],
  );

  useEffect(() => {
    const handleScroll = () => setShowBackToTop(window.scrollY > 520);
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // 目录滚动定位:非复刻路径的标题在主文档中,可直接按视口位置计算当前小节
  useEffect(() => {
    if (useWechatReplica || xArticleReplica || tocItems.length === 0) {
      return;
    }
    const syncActive = () => {
      let current = '';
      for (const item of tocItems) {
        const element = document.getElementById(item.id);
        if (element && element.getBoundingClientRect().top <= 150) {
          current = item.id;
        }
      }
      setActiveTocId(current);
    };
    syncActive();
    window.addEventListener('scroll', syncActive, { passive: true });
    return () => window.removeEventListener('scroll', syncActive);
  }, [tocItems, useWechatReplica, xArticleReplica]);

  useEffect(() => {
    // 列表接口不再携带正文,详情页始终从详情接口拉取完整文章;
    // store 命中时先用作占位,标题等元信息立即可见
    if (!id) return;
    // 列表数据不含正文,只有携带 content_md 的完整数据才可作占位直接渲染
    if (storeArticle?.content_md) {
      setArticle(storeArticle);
      setLoading(false);
    } else {
      setLoading(true);
    }
    fetch(`/api/v1/articles/${id}`)
      .then(res => {
        if (!res.ok) throw new Error('Article not found');
        return res.json();
      })
      .then(data => {
        setArticle(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        if (!storeArticle?.content_md) {
          setError(true);
          setLoading(false);
        }
      });
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
    // 微信一比一复刻视图的目录由 iframe 内脚本上报；X 正文是文档流渲染，走原生扫描
    if (useWechatReplica) {
      return;
    }
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
  }, [article, useWechatReplica]);

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
      <div className="empty-state" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
        <Loader2 size={16} className="animate-spin" />
        加载文章中…
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="empty-state">
        文章未找到，可能已被删除。
        <div style={{ marginTop: 12 }}>
          <Link to="/articles" className="text-link">返回文章库 <ArrowLeft size={13} /></Link>
        </div>
      </div>
    );
  }

  const xSections = article.source_type === 'x'
    ? extractXSections(article.content_md, article.summary)
    : null;

  // 普通推文的正文就是推文文字（长文走 bodyMarkdown，payload 只作兜底）
  const xTweetMarkdown = xSections?.payload?.tweet_text?.trim()
    ? xSections.payload.tweet_text
    : '';
  const xMediaItems = (xSections?.payload?.media_items ?? []).filter((item) => item.url);

  const markdownContent = xSections
    ? xSections.bodyMarkdown || xTweetMarkdown
    : wechatSections
    ? wechatSections.bodyMarkdown
    : article.content_md.includes(HTML_CONTENT_START)
      ? article.content_md.split(HTML_CONTENT_START)[0]
      : article.content_md;

  const htmlContent = wechatSections
    ? replicaHtmlContent
    : article.content_md.includes(HTML_CONTENT_START)
      ? article.content_md.split(HTML_CONTENT_START)[1].replace(HTML_CONTENT_END, '')
      : '';

  const xCreatedAt = xPreview?.created_at
    ? new Date(xPreview.created_at).toLocaleString('zh-CN', { hour12: false })
    : '';
  const isXArticle = article.source_type === 'x';

  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className={`reader-outer-row ${tocItems.length > 0 ? 'with-toc' : ''}`}>
        <nav className="reader-crumbs" aria-label="位置">
          <Link to="/articles">文章库</Link>
          <span>/</span>
          <span aria-current="page">{sourceLabel(article.source_type)}</span>
        </nav>
        <div className="reader-tools">
          <a
            className="reader-tool"
            href={article.original_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink size={13} /> 查看原文
          </a>
        </div>
      </div>

      <div className={`reader-layout ${tocItems.length > 0 ? 'has-toc' : ''}`}>
      <div className={isXArticle ? 'article-reader article-reader-x' : 'article-reader'}>
        {isXArticle ? (
          <header className="x-article-header">
            <div className="x-article-kicker"><span>{new Date(article.created_at).toLocaleDateString('zh-CN')}</span></div>
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
        ) : useWechatReplica ? null : (
          <header className="reader-top">
            <h1 className="reader-title">{article.title}</h1>
            <p className="reader-byline" style={{ '--src': sourceColor(article.source_type) } as React.CSSProperties}>
              <i aria-hidden="true" />
              {article.account_name ? <strong>{article.account_name}</strong> : null}
              <span>{sourceLabel(article.source_type)} · {new Date(article.created_at).toLocaleDateString('zh-CN')}</span>
            </p>
            {article.cover_image_url ? (
              <div className="reader-cover"><img src={article.cover_image_url} alt="" /></div>
            ) : null}
          </header>
        )}

        {/* Content */}
        <div className={isXArticle ? 'x-article-content' : 'reader-body'}>

          {wechatSections?.summaryMarkdown ? (
            <section className="reader-summary" aria-label="内容导读">
              <p className="reader-summary-label"><Sparkles size={12} />内容导读</p>
              <div className="md-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{wechatSections.summaryMarkdown}</ReactMarkdown>
              </div>
            </section>
          ) : null}

          <div ref={articleBodyRef} className="article-body-content">
              {useWechatReplica ? (
                <WechatArticleView
                  ref={wechatViewRef}
                  title={article.title}
                  htmlContent={replicaHtmlContent}
                  accountName={article.account_name}
                  publishTime={article.publish_time}
                  createdAt={article.created_at}
                  onTocItems={setTocItems}
                />
              ) : xArticleReplica ? (
                <XArticleView article={xArticleReplica} />
              ) : (
                <>
                  {xMediaItems.length > 0 ? (
                    <div className="x-article-media">
                      {xMediaItems.map((item, index) =>
                        item.type === 'photo' ? (
                          <img key={index} src={item.url} alt={`推文配图 ${index + 1}`} loading="lazy" />
                        ) : (
                          <video
                            key={index}
                            src={item.url}
                            poster={item.poster}
                            controls={item.type === 'video'}
                            playsInline
                            loop={item.type === 'gif'}
                            muted={item.type === 'gif'}
                            autoPlay={item.type === 'gif'}
                          />
                        ),
                      )}
                    </div>
                  ) : null}
                  {htmlContent ? (
                    <>
                      {markdownContent.trim() ? (
                        <div className={isXArticle ? 'x-article-markdown' : 'md-body'}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                            {markdownContent}
                          </ReactMarkdown>
                        </div>
                      ) : null}
                      <div
                        ref={htmlContainerRef}
                        className={`article-html-container w-full ${markdownContent.trim() ? 'reader-html-gap' : ''}`}
                        dangerouslySetInnerHTML={{ __html: htmlContent }}
                      />
                    </>
                  ) : article.source_type === 'x' && xPreview && !markdownContent.trim() ? null : (
                    <div className={isXArticle ? 'x-article-markdown' : 'md-body'}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                        {markdownContent}
                      </ReactMarkdown>
                    </div>
                  )}
                </>
              )}
            </div>
        </div>
      </div>
      {tocItems.length > 0 ? (
        <ArticleToc
          items={tocItems}
          activeId={activeTocId}
          preventDefaultJump={useWechatReplica}
          onNavigate={(item) => {
            if (useWechatReplica) {
              wechatViewRef.current?.scrollToTocItem(item.id);
            }
          }}
        />
      ) : null}
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
