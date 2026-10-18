import assert from 'node:assert/strict';
import test from 'node:test';
import { detectSourceFromUrl, normalizeContentUrl, SOURCE_META } from './contentSources.ts';

test('all supported platforms have selectable metadata and safe hostname detection', () => {
  assert.equal(Object.keys(SOURCE_META).length, 7);
  assert.equal(detectSourceFromUrl('https://youtu.be/BaW_jenozKc'), 'youtube');
  assert.equal(detectSourceFromUrl('https://v.douyin.com/abc/'), null);
  assert.equal(detectSourceFromUrl('blog.csdn.net/u/article/details/123'), 'csdn');
  assert.equal(detectSourceFromUrl('https://www.cnblogs.com/u/p/123.html'), 'cnblogs');
  assert.equal(detectSourceFromUrl('https://youtube.com.evil.test/?x=x.com'), 'other');
});

test('pasted share text extracts the actual link and rejects non-web protocols', () => {
  assert.equal(normalizeContentUrl('分享文案 https://youtu.be/BaW_jenozKc 复制打开'), 'https://youtu.be/BaW_jenozKc');
  assert.equal(normalizeContentUrl('javascript:alert(1)'), null);
  assert.equal(normalizeContentUrl('not a link'), null);
});

test('removed platform URLs cannot enter through generic webpage import', () => {
  for (const url of ['https://www.douyin.com/video/123', 'https://v.douyin.com/abc/', 'https://www.iesdouyin.com/share/video/123']) {
    assert.equal(normalizeContentUrl(url), null);
  }
});
