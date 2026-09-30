import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';

/**
 * 微信公众号文章一比一复刻视图（Shadow DOM 渲染）。
 *
 * 用 Shadow DOM 隔离站点样式：按 mp.weixin.qq.com 线上官方 CSS
 * （提取自 res.wx.qq.com 样式表 + 原文页面计算样式）渲染原文 HTML，
 * 并复刻微信页面 JS 的关键行为：
 *   - 图片懒加载属性转正（data-src → src）
 *   - 图片按 min(data-w, 可用宽度) 定宽、按 data-ratio 定高
 *   - visibility:hidden 修正
 * 正文 HTML 未经任何改写，内联样式原样生效，因此与原文一致。
 * 相比旧的 iframe 方案：无高度同步、无 sandbox、无跨窗消息，天然自适应高度。
 */

export interface WechatTocItem {
  id: string;
  text: string;
  level: number;
}

export interface WechatArticleViewHandle {
  scrollToTocItem: (id: string) => void;
}

interface WechatArticleViewProps {
  title: string;
  htmlContent: string;
  accountName?: string;
  publishTime?: string;
  createdAt?: string;
  onTocItems?: (items: WechatTocItem[]) => void;
}

/** 提取自 mp.weixin.qq.com 线上官方 CSS 的文章页核心规则（浅色模式）。 */
const WECHAT_PAGE_CSS = `
:host { all: initial; display: block; }
.wr-page {
  background: #fff;
  font-family: "PingFang SC NEW", system-ui, -apple-system, "Helvetica Neue", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -webkit-text-size-adjust: 100%;
}
.rich_media_area_primary { padding: 20px 20px 0; }
.rich_media_area_primary_inner { max-width: 677px; margin-left: auto; margin-right: auto; }
.rich_media_title {
  font-size: 22px;
  line-height: 1.4;
  font-weight: 500;
  color: rgba(0, 0, 0, .9);
  margin: 0 0 14px;
  word-wrap: break-word;
  -webkit-user-select: auto;
  user-select: auto;
}
.rich_media_meta { display: inline-block; vertical-align: middle; margin: 0 10px 10px 0; font-size: 15px; }
.rich_media_meta_text { color: rgba(0, 0, 0, .3); }
.rich_media_content {
  color: rgba(0, 0, 0, .9);
  font-size: 17px;
  line-height: 1.6;
  letter-spacing: .032em;
  text-align: justify;
  overflow: hidden;
  position: relative;
}
.rich_media_content * { max-width: 100% !important; box-sizing: border-box !important; -webkit-box-sizing: border-box !important; word-wrap: break-word !important; }
.rich_media_content p { clear: both; min-height: 1em; }
.rich_media_content em { font-style: italic; }
.rich_media_content fieldset { min-width: 0; }
.rich_media_content form { display: none !important; }
.rich_media_content img { height: auto !important; }
.rich_media_content:not(.old_list_style) .list-paddingleft-1,
.rich_media_content:not(.old_list_style) .list-paddingleft-2,
.rich_media_content:not(.old_list_style) .list-paddingleft-3 { padding-left: 2.2em; }
.rich_media_content:not(.old_list_style) .list-paddingleft-1 .list-paddingleft-2,
.rich_media_content:not(.old_list_style) .list-paddingleft-2 .list-paddingleft-2,
.rich_media_content:not(.old_list_style) .list-paddingleft-3 .list-paddingleft-2 { padding-left: 30px; }
.rich_media_content:not(.old_list_style) .list-paddingleft-1 { padding-left: 1.2em; }
.rich_media_content:not(.old_list_style) .list-paddingleft-3 { padding-left: 3.2em; }
.autoTypeSetting > p { margin-top: 0; margin-bottom: .5em; }
.autoTypeSetting24 > p { margin-top: 0; margin-bottom: 24px; }
.autoTypeSetting24psection > p { margin-top: 0; margin-bottom: 24px; }
.autoTypeSetting24psection > section { margin-top: 0; margin-bottom: 24px; }
.code-snippet, .code-snippet__fix, .code-snippet *, .code-snippet__fix * { max-width: 1000% !important; }
.code-snippet { margin: 10px 0; display: block; overflow-x: auto; font-size: 14px; padding: 1em 1em 1em 3em; color: #333; position: relative; background-color: #fafafa; border: 1px solid #f0f0f0; border-radius: 2px; counter-reset: line; white-space: normal; -webkit-overflow-scrolling: touch; }
.code-snippet code { text-align: left; font-size: 14px; display: block; white-space: pre-wrap; position: relative; font-family: Consolas, Liberation Mono, Menlo, Courier, monospace; }
.code-snippet code:before { position: absolute; min-width: 1.5em; text-align: right; left: -2.5em; counter-increment: line; content: counter(line); display: inline; margin-right: 12px; color: rgba(0, 0, 0, .15); }
.code-snippet_nowrap code { white-space: pre; display: flex; }
.code-snippet__fix { font-size: 14px; margin: 10px 0; display: flex; color: #333; position: relative; background-color: rgba(0, 0, 0, .03); border: 1px solid #f0f0f0; border-radius: 2px; line-height: 26px; }
.code-snippet__fix pre { overflow-x: auto; padding: 1em 1em 1em 0; white-space: normal; flex:  1; -webkit-overflow-scrolling: touch; }
.code-snippet__fix code { text-align: left; font-size: 14px; display: block; white-space: pre; position: relative; font-family: Consolas, Liberation Mono, Menlo, Courier, monospace; }
.code-snippet__fix .code-snippet__line-index { counter-reset: line; flex-shrink: 0; height: 100%; padding: 1em; list-style: none; }
.code-snippet__fix .code-snippet__line-index li { list-style-type: none; text-align: right; }
.code-snippet__fix .code-snippet__line-index li:before { min-width: 1.5em; text-align: right; left: -2.5em; counter-increment: line; content: counter(line); display: inline; color: rgba(0, 0, 0, .15); }
.code-snippet__comment, .code-snippet__quote { color: #afafaf; font-style: italic; }
`;

/** Shadow DOM 内的复刻运行时：懒加载转正、显隐修正、图片定宽、标题目录。返回 resize 清理函数。 */
function applyWechatRuntime(root: ShadowRoot, onTocItems?: (items: WechatTocItem[]) => void) {
  const content = root.querySelector('#js_content');
  if (!content) return;

  content.querySelectorAll<HTMLImageElement>('img[data-src]').forEach((img) => {
    if (!img.getAttribute('src')) img.setAttribute('src', img.getAttribute('data-src') || '');
  });
  root.querySelectorAll<HTMLElement>('[style]').forEach((el) => {
    if (/visibility\s*:\s*hidden/i.test(el.getAttribute('style') || '')) {
      el.style.visibility = 'visible';
    }
  });

  // 微信 JS 行为：图片按 min(data-w, 可用宽度) 定宽；
  // 高度不写死（官方 CSS height:auto!important 按图片真实比例），
  // aspect-ratio 仅在加载完成前用 data-ratio（高/宽比）占位防跳动
  const layoutImages = () => {
    content.querySelectorAll<HTMLImageElement>('img[data-w]').forEach((img) => {
      const w = parseFloat(img.getAttribute('data-w') || '');
      if (!w || Number.isNaN(w)) return;
      const parent = img.parentElement || content;
      const avail = (parent as HTMLElement).clientWidth || (content as HTMLElement).clientWidth;
      if (!avail) return;
      const width = Math.min(w, avail);
      const ratio = parseFloat(img.getAttribute('data-ratio') || '');
      let extra = `width: ${width}px !important; height: auto !important; visibility: visible !important;`;
      if (ratio > 0 && !Number.isNaN(ratio)) {
        extra += ` aspect-ratio: ${w} / ${Math.round(w * ratio)};`;
      }
      img.style.cssText = img.style.cssText
        .replace(/width:\s*[^;]+;?/g, '')
        .replace(/height:\s*[^;]+;?/g, '')
        .replace(/aspect-ratio:\s*[^;]+;?/g, '') + extra;
    });
  };
  layoutImages();
  window.addEventListener('resize', layoutImages);

  // 标题目录：编号并上报（文章 h1 标题不在 #js_content 内，不会被扫到）
  const tocItems: WechatTocItem[] = [];
  let seq = 0;
  content.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((h) => {
    if (!h.textContent?.trim()) return;
    seq += 1;
    h.id = `wx-toc-${seq}`;
    tocItems.push({ id: h.id, text: h.textContent.trim(), level: Number(h.tagName.slice(1)) });
  });
  onTocItems?.(tocItems);

  return layoutImages;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatPublishTime(raw: string): string {
  const value = (raw || '').trim();
  if (!value) return '';
  if (/^\d{13}$/.test(value)) {
    const date = new Date(Number(value));
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
    }
  }
  if (/^\d{10}$/.test(value)) {
    const date = new Date(Number(value) * 1000);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
    }
  }
  return value;
}

function buildMetaRow(accountName: string, publishTime: string): string {
  const parts: string[] = [];
  if (accountName) {
    parts.push('<span class="rich_media_meta rich_media_meta_text">' + escapeHtml(accountName) + '</span>');
  }
  if (publishTime) {
    parts.push('<span class="rich_media_meta rich_media_meta_text">' + escapeHtml(publishTime) + '</span>');
  }
  if (!parts.length) return '';
  return '<div id="meta_content" class="rich_media_meta_list">' + parts.join('') + '</div>';
}

function buildShadowHtml(title: string, htmlContent: string, accountName: string, publishTime: string): string {
  return `<style>${WECHAT_PAGE_CSS}</style>
<div class="wr-page">
<div class="rich_media_area_primary">
<div class="rich_media_area_primary_inner">
<h1 class="rich_media_title" id="activity-name"><span class="js_title_inner">${escapeHtml(title)}</span></h1>
${buildMetaRow(accountName, publishTime)}
${htmlContent}
</div>
</div>
</div>`;
}

const WechatArticleView = forwardRef<WechatArticleViewHandle, WechatArticleViewProps>(
  (
    { title, htmlContent, accountName, publishTime, createdAt, onTocItems },
    ref,
  ) => {
    const hostRef = useRef<HTMLDivElement>(null);
    const onTocItemsRef = useRef(onTocItems);
    onTocItemsRef.current = onTocItems;

    useEffect(() => {
      const host = hostRef.current;
      if (!host) return;
      const root = host.shadowRoot ?? host.attachShadow({ mode: 'open' });
      root.innerHTML = buildShadowHtml(
        title || '未知文章标题',
        htmlContent,
        (accountName || '').trim(),
        formatPublishTime(publishTime) || (createdAt ? new Date(createdAt).toLocaleDateString('zh-CN') : ''),
      );

      const cleanup = applyWechatRuntime(root, (items) => onTocItemsRef.current?.(items));
      return () => {
        if (cleanup) window.removeEventListener('resize', cleanup);
      };
    }, [title, htmlContent, accountName, publishTime, createdAt]);

    useImperativeHandle(ref, () => ({
      scrollToTocItem: (id: string) => {
        const root = hostRef.current?.shadowRoot;
        const el = root?.getElementById(id);
        if (!el) return;
        const top = el.getBoundingClientRect().top + window.scrollY - 76;
        window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
      },
    }));

    return <div ref={hostRef} className="wechat-replica-scope" role="article" aria-label={title || '微信公众号文章原文'} />;
  },
);

export default WechatArticleView;
