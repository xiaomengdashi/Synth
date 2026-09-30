import test from 'node:test';
import assert from 'node:assert/strict';
import { extractXArticle, buildXArticleDocument } from './xArticle.ts';

const replica = { version: 1, status: 'complete', title: '<测试>', body_html: '<p><strong>正文</strong></p><video src="/media/x/a.mp4" muted loop></video>', body_css: 'p{line-height:1.625}', text: '正文', cover_url: '/media/x/cover.jpg', author_name: '作者', author_handle:'author', author_avatar_url:'', created_at:'', source_url:'https://x.com/author/status/123', fonts:[], warnings:[], assets:[] };
test('reads only new replica marker, leaving legacy tweet and markdown alone', () => {
  const content = `摘要<!-- X_ARTICLE_START -->${JSON.stringify(replica)}<!-- X_ARTICLE_END -->`;
  assert.equal(extractXArticle(content)?.title, '<测试>');
  assert.equal(extractXArticle('<!-- X_CONTENT_START -->正文<!-- X_CONTENT_END -->'), null);
  assert.equal(extractXArticle('<!-- X_ARTICLE_START -->{}<!-- X_ARTICLE_END -->'), null);
});
test('isolates source CSS, escapes metadata, keeps media and locks scripts', () => {
  const parsed = extractXArticle(`<!-- X_ARTICLE_START -->${JSON.stringify(replica)}<!-- X_ARTICLE_END -->`)!;
  const html = buildXArticleDocument(parsed, 'https://local.test', 'test-nonce');
  assert.match(html, /&lt;测试&gt;/);
  assert.match(html, /<strong>正文<\/strong>/);
  assert.match(html, /<video/);
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /script-src 'nonce-test-nonce'/);
  assert.doesNotMatch(html, /allow-same-origin/);
});
test('text-only fallback never renders source text as HTML', () => {
  const parsed = extractXArticle(`<!-- X_ARTICLE_START -->${JSON.stringify({...replica,status:'text-only',body_html:'',text:'<script>bad</script>'})}<!-- X_ARTICLE_END -->`)!;
  assert.match(buildXArticleDocument(parsed,'https://local.test','n'), /&lt;script&gt;bad&lt;\/script&gt;/);
});
