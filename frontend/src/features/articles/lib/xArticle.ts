export interface XArticleReplica {
  version: 1;
  status: 'complete' | 'partial' | 'text-only';
  title: string;
  body_html: string;
  body_css: string;
  text: string;
  cover_url: string;
  author_name: string;
  author_handle: string;
  author_avatar_url: string;
  created_at: string;
  source_url: string;
  fonts: {url: string; weight: number}[];
  warnings: string[];
}

export function extractXArticle(content: string): XArticleReplica | null {
  const start = '<!-- X_ARTICLE_START -->';
  const end = '<!-- X_ARTICLE_END -->';
  const a = content.indexOf(start);
  const b = content.indexOf(end, a + start.length);
  if (a < 0 || b < 0) return null;
  try {
    const value = JSON.parse(content.slice(a + start.length, b));
    if (value?.version !== 1 || !['complete', 'partial', 'text-only'].includes(value.status)
      || typeof value.body_html !== 'string' || typeof value.text !== 'string' || typeof value.title !== 'string') return null;
    return {...value, body_css: typeof value.body_css === 'string' ? value.body_css : '',
      fonts: Array.isArray(value.fonts) ? value.fonts : [],
      warnings: Array.isArray(value.warnings) ? value.warnings.filter((v: unknown) => typeof v === 'string') : []};
  } catch { return null; }
}

function escapeHtml(value: string = ''): string {
  return value.replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]!));
}
function safeUrl(value: string = ''): string {
  if (/^\/media\/x\/[a-f0-9]+\.(?:jpg|jpeg|png|gif|webp|mp4|webm|woff2)$/.test(value)) return value;
  try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; }
  catch { return ''; }
}

export function buildXArticleDocument(article: XArticleReplica, origin: string, nonce: string, bodyOnly = false): string {
  const assetOrigin = new URL(origin).origin;
  const fonts = article.fonts.filter(f => /^\/media\/x\/[a-f0-9]+\.woff2$/.test(f.url) && [400,500,700].includes(f.weight))
    .map(f => `@font-face{font-family:TwitterChirp;src:url("${assetOrigin}${f.url}") format("woff2");font-weight:${f.weight};font-display:swap;}`).join('\n');
  const avatar = safeUrl(article.author_avatar_url);
  const cover = safeUrl(article.cover_url);
  const source = safeUrl(article.source_url);
  const date = article.created_at && !Number.isNaN(Date.parse(article.created_at))
    ? new Date(article.created_at).toLocaleString('zh-CN', {hour12:false}) : '';
  const body = article.body_html || `<div class="fallback-text">${escapeHtml(article.text)}</div>`;
  // bodyOnly：站点页头已展示标题/作者/封面，iframe 只渲染正文并铺满卡片宽度，
  // 字号行高贴近站点阅读节奏，避免"一篇文章里嵌另一套版式"的割裂感。
  const shell = bodyOnly
    ? '*{box-sizing:border-box}html{color-scheme:light;-webkit-text-size-adjust:100%;scrollbar-width:none}body{margin:0;background:#fff;color:#0f1419;font:16.5px/1.75 TwitterChirp,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}p,h1,h2,h3,h4,figure,ul,ol{margin:0}a{color:#1d9bf0;text-decoration:none}img,video{display:block;max-width:100%;height:auto}b,strong{font-weight:700}button{font:inherit}main{overflow-wrap:break-word}.fallback-text{white-space:pre-wrap;line-height:1.75}.x-article-body{font-size:16.5px;line-height:1.75}.x-article-body p{margin:0 0 18px;line-height:1.75;white-space:pre-wrap}.x-article-body h3{font-size:21px;line-height:1.4;font-weight:700;margin:28px 0 14px}.x-article-body figure{margin:26px 0;width:100%}.x-article-body ul,.x-article-body ol{margin:0 0 18px;padding-left:26px}.x-article-body ul{list-style-type:disc}.x-article-body ol{list-style-type:decimal}.x-article-body li{margin:5px 0}.x-article-body pre{overflow-x:auto;white-space:pre-wrap}.x-article-body blockquote{border-left:3px solid #cfd9de;padding-left:16px}.x-article-body table{border-collapse:collapse;max-width:100%}.x-article-body th,.x-article-body td{border:1px solid #cfd9de;padding:8px}.x-article-body video{width:100%;max-height:none!important}'
    : '*{box-sizing:border-box}html{color-scheme:light;-webkit-text-size-adjust:100%;scrollbar-width:none}body{margin:0;background:#fff;color:#0f1419;font:15px/20px TwitterChirp,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}p,h1,h2,h3,h4,figure,ul,ol{margin:0}a{color:#1d9bf0;text-decoration:none}img,video{display:block;max-width:100%;height:auto}b,strong{font-weight:700}button{font:inherit}main{max-width:600px;padding:16px;margin:auto;overflow-wrap:break-word}.source-author{display:flex;align-items:center;gap:8px;margin-bottom:20px}.source-author img{width:40px;height:40px;border-radius:50%;object-fit:cover}.source-author strong{display:block}.source-author small{font-size:15px;color:#536471}.source-cover{width:100%;aspect-ratio:5/2;object-fit:cover;margin-bottom:12px}.source-title{font-size:30px;line-height:36px;font-weight:800;margin:0 0 24px}.source-footer{color:#536471;margin-top:24px;padding-top:16px;border-top:1px solid #eff3f4}.fallback-text{white-space:pre-wrap;line-height:1.625}.x-article-body{font-size:15px;line-height:20px}.x-article-body p{margin:0 0 16px;line-height:1.625;white-space:pre-wrap}.x-article-body h3{font-size:20px;line-height:25px;font-weight:700;margin:24px 0 12px}.x-article-body figure{margin:24px 0;width:100%}.x-article-body ul,.x-article-body ol{margin:0 0 16px;padding-left:24px}.x-article-body ul{list-style-type:disc}.x-article-body ol{list-style-type:decimal}.x-article-body li{margin:4px 0}.x-article-body pre{overflow-x:auto;white-space:pre-wrap}.x-article-body blockquote{border-left:3px solid #cfd9de;padding-left:16px}.x-article-body table{border-collapse:collapse;max-width:100%}.x-article-body th,.x-article-body td{border:1px solid #cfd9de;padding:8px}.x-article-body video{width:100%;max-height:none!important}';
  // Source markup is sanitized on ingestion. The opaque sandbox and nonce-only
  // script policy provide an additional boundary around persisted source HTML.
  const head = bodyOnly ? '' : `<div class="source-author">${avatar ? `<img src="${escapeHtml(avatar)}" alt="">` : ''}<div><strong>${escapeHtml(article.author_name)}</strong><small>${article.author_handle ? '@' + escapeHtml(article.author_handle) : ''}</small></div></div>
${cover ? `<img class="source-cover" src="${escapeHtml(cover)}" alt="文章封面">` : ''}
<h1 class="source-title">${escapeHtml(article.title)}</h1>`;
  const foot = bodyOnly ? '' : `<footer class="source-footer">${escapeHtml(date)}${source ? ` · <a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">查看 X 原文</a>` : ''}</footer>`;
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${assetOrigin} https://pbs.twimg.com data:; media-src ${assetOrigin} https://video.twimg.com; font-src ${assetOrigin} https://abs.twimg.com; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'; base-uri 'none'; form-action 'none'">
<style>
${fonts}
${shell}
${article.body_css.replace(/<\/style/gi, '<\\/style')}
</style></head><body><main>
${head}${body}
${foot}</main>
<script nonce="${nonce}">
const send=()=>parent.postMessage({type:'x-replica-height',height:Math.ceil(document.documentElement.scrollHeight)},'*');
const headings=Array.from(document.querySelectorAll('.x-article-body h1,.x-article-body h2,.x-article-body h3,.x-article-body h4,.x-article-body h5,.x-article-body h6'));
const toc=headings.map((e,i)=>{e.id='x-section-'+i;return {id:e.id,text:e.textContent.trim(),level:Number(e.tagName.slice(1))}});
parent.postMessage({type:'x-replica-toc',items:toc},'*');
new ResizeObserver(send).observe(document.querySelector('main'));
addEventListener('load',send);document.fonts.ready.then(send);send();
addEventListener('message',e=>{if(e.source!==parent||e.data?.type!=='x-replica-scroll')return;const target=headings.find(h=>h.id===e.data.id);if(target)parent.postMessage({type:'x-replica-scroll-pos',top:target.getBoundingClientRect().top+scrollY},'*')});
</script></body></html>`;
}
