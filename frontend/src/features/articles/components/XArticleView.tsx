import { memo, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { XArticleReplica } from '../lib/xArticle';

/**
 * X 长文正文渲染：直接进入站点文档流（不再用 iframe）。
 *
 * body_html 在后端入库前已做白名单清洗（仅保留白名单标签/属性，
 * URL 限定 pbs.twimg.com / video.twimg.com / /media/x/，无 script），
 * 因此可以安全地以静态 HTML 插入。文档流渲染消除了巨型跨进程 iframe
 * 的滚动光栅化卡顿，目录与锚点跳转回归原生 DOM 行为。
 *
 * text-only 降级（原页补采失败）时 body_html 为空，text 是
 * render_twitter_article_result 输出的 Markdown（含行内加粗/斜体/
 * 删除线/下划线/行内代码与链接），按 Markdown 渲染而不是当纯文本转义，
 * 避免 `**加粗**` 这类记号原样显示。
 */
const XArticleView = memo(function XArticleView({ article }: { article: XArticleReplica }) {
  const bodyHtml = useMemo(() => article.body_html, [article]);

  // 本地化的 TwitterChirp 字体按需注册一次
  useEffect(() => {
    const fonts = article.fonts.filter(
      (f) => /^\/media\/x\/[a-f0-9]+\.woff2$/.test(f.url) && [400, 500, 700].includes(f.weight),
    );
    if (!fonts.length) return;
    const styleId = 'x-article-fonts';
    if (document.getElementById(styleId)) return;
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = fonts
      .map((f) => `@font-face{font-family:TwitterChirp;src:url("${f.url}") format("woff2");font-weight:${f.weight};font-display:swap;}`)
      .join('\n');
    document.head.appendChild(style);
  }, [article]);

  return (
    <>
      {article.warnings.length > 0 ? (
        <div className="x-replica-warning" role="note">
          {article.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      ) : null}
      {bodyHtml ? (
        <section
          className="x-source-body"
          // 内容在后端入库前经白名单清洗，详见 backend/app/services/fetchers/x_article.py
          dangerouslySetInnerHTML={{ __html: bodyHtml }}
        />
      ) : (
        // text-only 降级：正文只有 Markdown 文本时按站点阅读版式渲染 Markdown
        <div className="x-article-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{article.text}</ReactMarkdown>
        </div>
      )}
    </>
  );
});

export default XArticleView;
