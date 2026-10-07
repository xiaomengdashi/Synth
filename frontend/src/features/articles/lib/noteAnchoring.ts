/**
 * 划线笔记文本锚定(纯函数,无 DOM 引用,node:test 可测)。
 *
 * 锚定方案:quote+前后文指纹(prefix/suffix 各 CONTEXT_RADIUS 字符)的纯文本匹配,
 * 不用 DOM 路径——正文重渲染/图片后到改布局/hljs 二次改写代码块都不影响文本匹配,
 * 命中后由调用方把字符区间切回逐文本节点构造 Range(Range 跟随 reflow 天然免疫布局变化)。
 *
 * 保存与恢复共用同一 collectTextBlocks 字符流口径(见 noteHighlight.ts),
 * 保证偏移语义一致:haystack=内容根全部文本节点按文档序无分隔符拼接。
 */

/** 前后文指纹半径:各取划线边界外 32 字符,入库列宽 128 留余量 */
export const CONTEXT_RADIUS = 32;
/** 划线原文上限,与后端 pydantic max_length 对齐 */
export const MAX_QUOTE_LENGTH = 2000;

/**
 * 把连续空白(含换行/制表)折叠为单空格,并保留归一化位置→原始偏移的映射。
 * map[k] = normalized[k] 这个字符所代表的原始偏移(空白段指向该段最后一个字符),
 * 供归一化匹配命中后换算回原始切片区间。
 */
export function buildNormalizedIndex(text: string): { normalized: string; map: number[] } {
  const map: number[] = [];
  let normalized = '';
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      let j = i;
      while (j < text.length && /\s/.test(text[j])) j += 1;
      normalized += ' ';
      map.push(j - 1);
      i = j;
    } else {
      normalized += ch;
      map.push(i);
      i += 1;
    }
  }
  return { normalized, map };
}

function findQuoteOccurrences(haystack: string, needle: string): number[] {
  const positions: number[] = [];
  let index = haystack.indexOf(needle);
  while (index >= 0) {
    positions.push(index);
    index = haystack.indexOf(needle, index + 1);
  }
  return positions;
}

/** 上下文重合度:两者长度不一时先对齐(prefix 右对齐——都与 quote 起点相邻,suffix 左对齐),再逐位比较 */
function overlapScore(stored: string, actual: string, align: 'start' | 'end'): number {
  if (!stored.length || !actual.length) return 0;
  let left = stored;
  let right = actual;
  if (stored.length > actual.length) {
    left = align === 'end' ? stored.slice(stored.length - actual.length) : stored.slice(0, actual.length);
  } else if (actual.length > stored.length) {
    right = align === 'end' ? actual.slice(actual.length - stored.length) : actual.slice(0, stored.length);
  }
  let score = 0;
  for (let i = 0; i < left.length && i < right.length; i += 1) {
    if (left[i] === right[i]) score += 1;
  }
  return score;
}

/** 枚举 quote 全部出现位置,按前后文重合数打分取最高(并列取先);无出现返回 null */
function bestByContext(
  haystack: string,
  quote: string,
  prefix: string,
  suffix: string,
): [number, number] | null {
  const positions = findQuoteOccurrences(haystack, quote);
  if (positions.length === 0) return null;
  let best = positions[0];
  let bestScore = -1;
  for (const position of positions) {
    const actualPrefix = haystack.slice(Math.max(0, position - prefix.length), position);
    const actualSuffix = haystack.slice(position + quote.length, position + quote.length + suffix.length);
    const score = overlapScore(prefix, actualPrefix, 'end') + overlapScore(suffix, actualSuffix, 'start');
    if (score > bestScore) {
      bestScore = score;
      best = position;
    }
  }
  return [best, best + quote.length];
}

/**
 * 三级匹配策略:
 * ① 精确 indexOf(prefix+quote+suffix) 一次命中即用(前缀不存在=文首、后缀不存在=文末,
 *    indexOf 空串=0 语义天然覆盖);
 * ② 原文枚举打分:quote 多次出现按上下文重合数取最高,单次出现直接用;
 * ③ 归一化管道:原文含换行/多空白差异(微信 HTML 常见)时,双方空白折叠后重匹配,
 *    经 map[] 换算回原始偏移;
 * ④ 全部失败返回 null——优雅降级:不画高亮,列表行照常显示 quote 与笔记,不渲染「定位」。
 */
export function findAnchorRange(
  haystack: string,
  quote: string,
  prefix = '',
  suffix = '',
): [number, number] | null {
  if (!haystack || !quote) return null;

  const exact = haystack.indexOf(prefix + quote + suffix);
  if (exact >= 0) {
    const start = exact + prefix.length;
    return [start, start + quote.length];
  }

  const raw = bestByContext(haystack, quote, prefix, suffix);
  if (raw) return raw;

  const { normalized, map } = buildNormalizedIndex(haystack);
  const normalizedQuote = buildNormalizedIndex(quote).normalized;
  if (!normalizedQuote) return null;
  const normalizedHit = bestByContext(
    normalized,
    normalizedQuote,
    buildNormalizedIndex(prefix).normalized,
    buildNormalizedIndex(suffix).normalized,
  );
  if (!normalizedHit) return null;
  const start = map[normalizedHit[0]];
  const end = map[normalizedHit[1] - 1] + 1;
  if (start === undefined || end === undefined || end <= start || end > haystack.length) return null;
  return [start, end];
}

/** 文本块的最小结构:node 上的 [start,end) 字符区间(连续偏移坐标系) */
export interface TextBlockLike<T> {
  node: T;
  start: number;
  end: number;
}

/**
 * 通用泛型块切片:把字符区间 [charStart, charEnd) 切到逐块内的局部偏移。
 * 跨块/块内/半块边界自动钳制,空区间(与块无交集或钳后为空)丢弃。
 */
export function sliceRange<T>(blocks: TextBlockLike<T>[], charStart: number, charEnd: number): TextBlockLike<T>[] {
  const hits: TextBlockLike<T>[] = [];
  for (const block of blocks) {
    if (block.end <= charStart || block.start >= charEnd) continue;
    const start = Math.max(block.start, charStart) - block.start;
    const end = Math.min(block.end, charEnd) - block.start;
    if (end > start) hits.push({ node: block.node, start, end });
  }
  return hits;
}

/** 同文章内是否已有完全相同的划线(quote 全等判定,防重复) */
export function hasSameQuote<T extends { quote: string }>(notes: T[], quote: string): boolean {
  return notes.some((note) => note.quote === quote);
}
