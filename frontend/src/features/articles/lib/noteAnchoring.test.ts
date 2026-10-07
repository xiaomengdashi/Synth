import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CONTEXT_RADIUS,
  MAX_QUOTE_LENGTH,
  buildNormalizedIndex,
  findAnchorRange,
  hasSameQuote,
  sliceRange,
} from './noteAnchoring.ts';

test('buildNormalizedIndex 折叠空白并保留原始偏移映射', () => {
  const { normalized, map } = buildNormalizedIndex('a  b\n\nc\t d');
  // 三段空白各折叠为一个空格
  assert.equal(normalized, 'a b c d');
  // 逐字符回映:a(0) 空格(→原2,空白段末字符) b(→原3) 空格(→原5) c(→原6) 空格(→原8) d(→原9)
  assert.equal(map.length, normalized.length);
  assert.equal(map[0], 0);
  assert.equal(map[1], 2);
  assert.equal(map[2], 3);
  assert.equal(map[3], 5);
  assert.equal(map[4], 6);
  assert.equal(map[5], 8);
  assert.equal(map[6], 9);
  // 无空白文本:恒等映射
  const plain = buildNormalizedIndex('abc');
  assert.equal(plain.normalized, 'abc');
  assert.deepEqual(plain.map, [0, 1, 2]);
});

test('常量与后端约束对齐', () => {
  assert.equal(CONTEXT_RADIUS, 32);
  assert.equal(MAX_QUOTE_LENGTH, 2000);
});

test('findAnchorRange 精确 prefix+quote+suffix 一次命中', () => {
  const haystack = '前文指纹这里是划线的原文内容后文指纹尾巴';
  const quote = '这里是划线的原文内容';
  const start = haystack.indexOf(quote);
  const anchor = findAnchorRange(haystack, quote, '前文指纹', '后文指纹');
  assert.deepEqual(anchor, [start, start + quote.length]);
});

test('quote 多次出现按上下文打分取对', () => {
  // 保存时上下文是 'ABC'+quote+'DEF'(连续);恢复后正文里指纹首字符被改(C→X),
  // 精确拼接失败,只能枚举 quote 出现位置按上下文重合数打分
  const text = 'ABX甲重复DEF中间文字zz甲重复zzz';
  const anchor = findAnchorRange(text, '甲重复', 'ABC', 'DEF');
  const expect = text.indexOf('甲重复');
  // 第一次出现:前缀 ABX 对 2 分+后缀 DEF 对 3 分,胜过第二次(全 0 分)
  assert.deepEqual(anchor, [expect, expect + '甲重复'.length]);

  // 同样的 quote,把高分上下文换到第二次出现上,应命中后者
  const text2 = 'zz甲重复qqq中间文字ABX甲重复DEF';
  const anchor2 = findAnchorRange(text2, '甲重复', 'ABC', 'DEF');
  const expect2 = text2.lastIndexOf('甲重复');
  assert.deepEqual(anchor2, [expect2, expect2 + '甲重复'.length]);

  // 无上下文信息(空指纹)时取首次出现
  const anchor3 = findAnchorRange(text, '甲重复', '', '');
  assert.deepEqual(anchor3, [expect, expect + '甲重复'.length]);
});

test('文首/文尾的空 prefix/suffix 自然命中', () => {
  const haystack = '开头就是划线中间还有一段结尾也是划线';
  // quote 在文首:prefix 为空,indexOf(quote+suffix) 直接命中
  const head = findAnchorRange(haystack, '开头就是划线', '', '中间还有');
  assert.deepEqual(head, [0, '开头就是划线'.length]);
  // quote 在文尾:suffix 为空
  const tailQuote = '结尾也是划线';
  const tail = findAnchorRange(haystack, tailQuote, '中间还有一段', '');
  assert.deepEqual(tail, [haystack.length - tailQuote.length, haystack.length]);
});

test('换行/空白差异经归一化管道命中并映射回原始偏移', () => {
  // 保存时正文是 "第一段\n\n第二段"(选区跨段含换行);重进后 DOM 收集到多空格变体
  const savedHaystack = '第一段\n\n第二段';
  const start = savedHaystack.indexOf('段\n\n第');
  const quote = savedHaystack.slice(start, start + 4); // '段\n\n第'
  const prefix = savedHaystack.slice(Math.max(0, start - 32), start);
  const suffix = savedHaystack.slice(start + 4, start + 4 + 32);
  // 恢复时同一位置的换行变成了两个空格
  const restoredHaystack = savedHaystack.replace('\n\n', '  ');
  const anchor = findAnchorRange(restoredHaystack, quote, prefix, suffix);
  assert.ok(anchor);
  const [a, b] = anchor;
  assert.equal(restoredHaystack.slice(a, b), '段  第');
  // 恢复后的正文里找不到原样 quote(换行≠空格),①②两级都失败,只有归一化管道能救
  assert.equal(restoredHaystack.indexOf(quote), -1);
});

test('完全不存在返回 null(降级:不画高亮,列表照常)', () => {
  assert.equal(findAnchorRange('完全不同的正文', '不存在的划线', '前', '后'), null);
  assert.equal(findAnchorRange('', '划线'), null);
  assert.equal(findAnchorRange('正文', ''), null);
  // 归一化后仍找不到(字符本质不同,仅空白差异救不了)
  assert.equal(findAnchorRange('甲乙丙丁', '戊己', '', ''), null);
});

test('sliceRange 块内切片/跨多块/半块边界钳制/空区间丢弃', () => {
  // 假 node 对象,无 DOM 依赖
  const blocks = [
    { node: { id: 'a' }, start: 0, end: 5 },
    { node: { id: 'b' }, start: 5, end: 10 },
    { node: { id: 'c' }, start: 10, end: 15 },
  ];
  // 块内切片:区间完全落在第一块内
  assert.deepEqual(sliceRange(blocks, 1, 4), [{ node: { id: 'a' }, start: 1, end: 4 }]);
  // 跨多块:中间块整块命中,两端块半块钳制
  assert.deepEqual(sliceRange(blocks, 3, 12), [
    { node: { id: 'a' }, start: 3, end: 5 },
    { node: { id: 'b' }, start: 0, end: 5 },
    { node: { id: 'c' }, start: 0, end: 2 },
  ]);
  // 边界恰好贴合块边界:不产生空块
  assert.deepEqual(sliceRange(blocks, 5, 10), [{ node: { id: 'b' }, start: 0, end: 5 }]);
  // 空区间/无交集丢弃
  assert.deepEqual(sliceRange(blocks, 4, 4), []);
  assert.deepEqual(sliceRange(blocks, 20, 30), []);
  assert.deepEqual(sliceRange([], 0, 5), []);
});

test('hasSameQuote 按 quote 全等去重', () => {
  const notes = [{ id: '1', quote: '同一段' }, { id: '2', quote: '另一段' }];
  assert.equal(hasSameQuote(notes, '同一段'), true);
  assert.equal(hasSameQuote(notes, '不在库里'), false);
  // 轻微改选区(多一个字)不算重复——与后端 409 同口径
  assert.equal(hasSameQuote(notes, '同一段落'), false);
  assert.equal(hasSameQuote([], '任意'), false);
});
