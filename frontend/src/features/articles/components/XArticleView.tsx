import { memo, useEffect, useMemo } from 'react';
import type { XArticleReplica } from '../lib/xArticle';

/**
 * X 长文正文渲染：直接进入站点文档流（不再用 iframe）。
 *
 * body_html 在后端入库前已做白名单清洗（仅保留白名单标签/属性，
 * URL 限定 pbs.twimg.com / video.twimg.com / /media/x/，无 script），
 * 因此可以安全地以静态 HTML 插入。文档流渲染消除了巨型跨进程 iframe
 * 的滚动光栅化卡顿，目录与锚点跳转回归原生 DOM 行为。
 */
const XArticleView = memo(function XArticleView({ article }: { article: XArticleReplica }) {
  const bodyHtml = useMemo(
    () => article.body_html || `<div class="fallback-text">${escapeText(article.text)}</div>`,
    [article],
  );

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
    <section
      className="x-source-body"
      // 内容在后端入库前经白名单清洗，详见 backend/app/services/fetchers/x_article.py
      dangerouslySetInnerHTML={{ __html: bodyHtml }}
    />
  );
});

function escapeText(value = ''): string {
  return value.replace(/[&<>"']/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!
  ));
}

export default XArticleView;
