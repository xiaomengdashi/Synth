/**
 * 划线笔记 DOM 适配层(不单测,依赖浏览器 DOM;纯逻辑全部在 noteAnchoring.ts)。
 *
 * 两条渲染路径的机制不可互换:
 * - 主文档(md 正文/X 复刻/HTML 导入,文本节点由 React 管理):必须走 CSS Custom
 *   Highlight API(CSS.highlights 注册 Range + ::highlight() 上色)——零 DOM 改写,
 *   直接包 <span> 会与 React reconciliation 冲突(切文章重渲染时 split text node
 *   可致 NotFoundError)。
 * - 微信 Shadow DOM 复刻(React 不进 shadow 树,innerHTML 在 effect 里整体重写):
 *   CSS Custom Highlight 不穿入 shadow 树,必须逐 Range 包 <span data-note-id>
 *   内联样式——此处安全恰因 React 不 reconcile shadow 树。
 */

import { CONTEXT_RADIUS, findAnchorRange, sliceRange } from './noteAnchoring';

/** 主文档高亮的注册名(见 index.css 的 ::highlight(article-note)) */
export const NOTE_HIGHLIGHT_NAME = 'article-note';
/** 定位闪烁的第二个注册名,不复用常亮高亮避免互相覆盖 */
export const NOTE_FLASH_NAME = 'article-note-flash';

/** 马克笔语义固定黄:与 index.css ::highlight(article-note) 同色值;shadow 内 span 内联用 */
export const NOTE_HIGHLIGHT_BACKGROUND = 'rgba(255, 212, 0, .38)';
const NOTE_FLASH_BACKGROUND = 'rgba(255, 212, 0, .62)';

// TS 5.8 的 lib.dom 尚未收录 Selection.getComposedRanges(Chromium 128+ 的选区规范扩展),
// 此处局部声明补类型,不动 tsconfig
declare global {
  interface Selection {
    getComposedRanges?(options?: { shadowRoots?: ShadowRoot[] }): AbstractRange[];
  }
}

/**
 * 取「完整落在内容根内」的活选区区间。
 * Chromium/Edge 154 起,真实选区落在 open shadow 树内时 document.getSelection() 只回
 * 净化视图(isCollapsed:true、anchorNode 在光 DOM),旧接口取不到——此时用
 * getComposedRanges({shadowRoots}) 取回真区间并重建 document Range(composed 返回的
 * 是静态区间,无 getBoundingClientRect 等);Firefox/Safari 的 getSelection 仍直接
 * 返回 shadow 树内节点,走前一分支。两者都取不到返回 null。
 */
export function getActiveRangeInRoot(root: Element | ShadowRoot | null): Range | null {
  if (!root) return null;
  const scope: Node = root;
  const contains = (node: Node | null): boolean => Boolean(node && scope.contains(node));
  const selection = document.getSelection();
  if (selection && selection.rangeCount > 0 && !selection.isCollapsed) {
    const range = selection.getRangeAt(0);
    if (contains(range.startContainer) && contains(range.endContainer)) return range;
  }
  if (!(root instanceof ShadowRoot) || !selection || typeof selection.getComposedRanges !== 'function') {
    return null;
  }
  try {
    const composed = selection.getComposedRanges({ shadowRoots: [root] }) || [];
    for (const item of composed) {
      if (item.collapsed) continue;
      if (!contains(item.startContainer) || !contains(item.endContainer)) continue;
      const ownerDocument = item.startContainer.ownerDocument ?? document;
      const range = ownerDocument.createRange();
      range.setStart(item.startContainer, item.startOffset);
      range.setEnd(item.endContainer, item.endOffset);
      return range;
    }
  } catch {
    // 实现差异时静默降级(等同无选区)
  }
  return null;
}

export interface TextBlock<TNode = Node> {
  node: TNode;
  start: number;
  end: number;
}

export interface NoteAnchorInput {
  id: string;
  quote: string;
  prefix?: string;
  suffix?: string;
}

export function blocksText(blocks: TextBlock[]): string {
  let text = '';
  for (const block of blocks) {
    text += (block.node as Text).nodeValue || '';
  }
  return text;
}

/** 收集内容根全部文本节点,按文档序拼成连续字符索引块(textContent 语义,无分隔符) */
export function collectTextBlocks(root: Document | ShadowRoot | Element): TextBlock[] {
  const container = root instanceof ShadowRoot || root instanceof Element ? root : root.body;
  if (!container) return [];
  const walker = (container.ownerDocument ?? document).createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const blocks: TextBlock[] = [];
  let offset = 0;
  let current = walker.nextNode();
  while (current) {
    const text = current.nodeValue || '';
    if (text.length > 0) {
      blocks.push({ node: current, start: offset, end: offset + text.length });
      offset += text.length;
    }
    current = walker.nextNode();
  }
  return blocks;
}

/**
 * 选区边界→字符偏移。文本节点直接命中;元素边界(三击选段)用探测 Range 与各块比较;
 * 完全在块外的边界(选区起/终点越过内容根)按方向钳到首/末块端点(调用方保证选区
 * 至少一端在内容根内才会走到这里)。
 */
function boundaryOffset(blocks: TextBlock[], container: Node, offset: number, direction: 'start' | 'end'): number {
  for (const block of blocks) {
    if (block.node === container) {
      return block.start + Math.min(Math.max(offset, 0), block.end - block.start);
    }
  }
  const clamp = () => (direction === 'start' ? blocks[0].start : blocks[blocks.length - 1].end);
  if (container.nodeType !== Node.TEXT_NODE) {
    const ownerDocument = container.ownerDocument ?? document;
    const probe = ownerDocument.createRange();
    const cursor = ownerDocument.createRange();
    try {
      probe.setStart(container, Math.min(Math.max(offset, 0), container.childNodes.length));
      probe.collapse(true);
    } catch {
      return clamp();
    }
    for (let index = 0; index < blocks.length; index += 1) {
      const block = blocks[index];
      try {
        cursor.setStart(block.node, 0);
        cursor.setEnd(block.node, block.end - block.start);
      } catch {
        continue;
      }
      // probe 落在本块开始之前:起点取本块起点,终点取上一块终点
      if (probe.compareBoundaryPoints(Range.END_TO_START, cursor) < 0) {
        return direction === 'start' ? block.start : (index > 0 ? blocks[index - 1].end : block.start);
      }
      // probe 落在本块内:按方向取本块起/终点
      if (probe.compareBoundaryPoints(Range.START_TO_END, cursor) <= 0) {
        return direction === 'start' ? block.start : block.end;
      }
    }
  }
  return clamp();
}

/** 由活选区构造锚点:quote/prefix/suffix 从同一字符流切片,保存与恢复口径一致 */
export function buildAnchorFromSelection(
  blocks: TextBlock[],
  range: Range,
): { quote: string; prefix: string; suffix: string } | null {
  if (blocks.length === 0) return null;
  const start = boundaryOffset(blocks, range.startContainer, range.startOffset, 'start');
  const end = boundaryOffset(blocks, range.endContainer, range.endOffset, 'end');
  if (end <= start) return null;
  const haystack = blocksText(blocks);
  return {
    quote: haystack.slice(start, end),
    prefix: haystack.slice(Math.max(0, start - CONTEXT_RADIUS), start),
    suffix: haystack.slice(end, end + CONTEXT_RADIUS),
  };
}

/** 对每条笔记执行三级文本锚定,切回逐文本节点的 DOM Range;锚定失败(null)跳过该条 */
export function rangesForNotes(notes: NoteAnchorInput[], root: Document | ShadowRoot | Element): Map<string, Range[]> {
  const result = new Map<string, Range[]>();
  if (!notes.length) return result;
  const blocks = collectTextBlocks(root);
  if (!blocks.length) return result;
  const haystack = blocksText(blocks);
  const ownerDocument = (root instanceof ShadowRoot ? root.host.ownerDocument : (root as Element).ownerDocument) ?? document;
  for (const note of notes) {
    const anchor = findAnchorRange(haystack, note.quote, note.prefix || '', note.suffix || '');
    if (!anchor) continue;
    const parts = sliceRange(blocks, anchor[0], anchor[1]);
    const ranges: Range[] = [];
    for (const part of parts) {
      const range = ownerDocument.createRange();
      try {
        range.setStart(part.node, part.start);
        range.setEnd(part.node, part.end);
        ranges.push(range);
      } catch {
        // 节点已变化的块放弃(锚定失败的降级路径)
      }
    }
    if (ranges.length) result.set(note.id, ranges);
  }
  return result;
}

function supportsCssHighlights(): boolean {
  return typeof Highlight !== 'undefined' && typeof CSS !== 'undefined' && Boolean(CSS.highlights);
}

/** 主文档路径:一个 Highlight 装全部笔记的 ranges,注册名覆盖式替换;不支持时静默 false */
export function applyDocumentHighlights(map: Map<string, Range[]>): boolean {
  if (!supportsCssHighlights()) return false;
  const ranges: Range[] = [];
  for (const list of map.values()) ranges.push(...list);
  CSS.highlights.set(NOTE_HIGHLIGHT_NAME, new Highlight(...ranges));
  return true;
}

export function clearDocumentHighlights(): void {
  if (typeof CSS === 'undefined' || !CSS.highlights) return;
  CSS.highlights.delete(NOTE_HIGHLIGHT_NAME);
  CSS.highlights.delete(NOTE_FLASH_NAME);
}

/** 主文档定位闪烁:第二注册名临时注册,1.6s 后移除 */
export function flashDocumentRange(range: Range, durationMs = 1600): void {
  if (!supportsCssHighlights()) return;
  CSS.highlights.set(NOTE_FLASH_NAME, new Highlight(range));
  window.setTimeout(() => {
    if (typeof CSS !== 'undefined' && CSS.highlights) CSS.highlights.delete(NOTE_FLASH_NAME);
  }, durationMs);
}

function wrapRangeWithSpan(range: Range, noteId: string, background: string): void {
  const root = range.commonAncestorContainer;
  const walkerRoot = root.nodeType === Node.TEXT_NODE ? root.parentNode : root;
  if (!walkerRoot) return;
  const walker = (walkerRoot.ownerDocument ?? document).createTreeWalker(walkerRoot, NodeFilter.SHOW_TEXT);
  const targets: Text[] = [];
  let current = walker.nextNode();
  while (current) {
    if (range.intersectsNode(current) && (current.nodeValue || '').length > 0) targets.push(current as Text);
    current = walker.nextNode();
  }
  for (const text of targets) {
    let start = 0;
    let end = text.nodeValue?.length ?? 0;
    if (text === range.startContainer) start = range.startOffset;
    if (text === range.endContainer) end = range.endOffset;
    if (end <= start) continue;
    const span = (text.ownerDocument ?? document).createElement('span');
    span.setAttribute('data-note-id', noteId);
    span.style.background = background;
    try {
      // splitText 把选区外的尾巴切走,再包住选区子串(仅 shadow 树内执行,React 不进)
      if (end < (text.nodeValue?.length ?? 0)) text.splitText(end);
      const selected = start > 0 ? text.splitText(start) : text;
      selected.parentNode?.insertBefore(span, selected);
      span.appendChild(selected);
    } catch {
      // 节点被并发改动时放弃该块
    }
  }
}

/** shadow 路径整体重包。⚠️ 调用方必须先 unwrapShadowHighlights 再 rangesForNotes 再调本函数:
 * unwrap 的 parent.normalize() 会合并 wrap 时 splitText 出的文本节点,若带着旧 span 先算
 * Range 再 unwrap,刚算好的 Range 边界节点会随 normalize 失联而被静默丢弃(高亮消失)。
 * 内部再 unwrap 一次仅作幂等兜底(干净 DOM 上为空操作)。 */
export function applyShadowHighlights(shadowRoot: ShadowRoot, map: Map<string, Range[]>): void {
  unwrapShadowHighlights(shadowRoot);
  for (const [noteId, ranges] of map) {
    for (const range of ranges) {
      wrapRangeWithSpan(range, noteId, NOTE_HIGHLIGHT_BACKGROUND);
    }
  }
}

export function unwrapShadowHighlights(shadowRoot: ShadowRoot): void {
  shadowRoot.querySelectorAll('span[data-note-id]').forEach((span) => {
    const parent = span.parentNode;
    if (!parent) return;
    while (span.firstChild) parent.insertBefore(span.firstChild, span);
    parent.removeChild(span);
    parent.normalize();
  });
}

/** shadow 路径定位闪烁:给该笔记的全部 span 临时换高亮底色后还原 */
export function flashShadowNote(shadowRoot: ShadowRoot, noteId: string, durationMs = 1600): void {
  const spans = Array.from(shadowRoot.querySelectorAll(`span[data-note-id="${noteId}"]`)) as HTMLElement[];
  if (!spans.length) return;
  spans.forEach((span) => { span.style.background = NOTE_FLASH_BACKGROUND; });
  window.setTimeout(() => {
    spans.forEach((span) => { span.style.background = NOTE_HIGHLIGHT_BACKGROUND; });
  }, durationMs);
}
