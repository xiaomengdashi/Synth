export const SOURCE_META = {
  wechat: { label: '微信公众号', short: '微信', placeholder: '粘贴微信公众号文章链接', color: 'var(--wechat)', domains: ['mp.weixin.qq.com'] },
  x: { label: 'X / Twitter', short: 'X', placeholder: '粘贴 X 帖子或长文的推文链接', color: 'var(--x-blue)', domains: ['x.com', 'twitter.com'] },
  bilibili: { label: 'Bilibili', short: 'B 站', placeholder: '粘贴 B 站视频链接', color: 'var(--bili)', domains: ['bilibili.com', 'b23.tv'] },
  youtube: { label: 'YouTube', short: 'YouTube', placeholder: '粘贴 YouTube 视频或 Shorts 链接', color: 'var(--faint)', domains: ['youtube.com', 'youtu.be'] },
  csdn: { label: 'CSDN', short: 'CSDN', placeholder: '粘贴 CSDN 文章链接', color: 'var(--faint)', domains: ['csdn.net'] },
  cnblogs: { label: '博客园', short: '博客园', placeholder: '粘贴博客园文章链接', color: 'var(--faint)', domains: ['cnblogs.com'] },
  other: { label: '其他网页', short: '网页', placeholder: '粘贴公开网页或博客链接', color: 'var(--faint)', domains: [] },
} as const;

export type Source = keyof typeof SOURCE_META;

export function normalizeContentUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const candidate = trimmed.match(/https?:\/\/[^\s<>"'，。；！？]+/i)?.[0] ?? trimmed;
  try {
    const parsed = new URL(/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(candidate) ? candidate : `https://${candidate}`);
    if (['douyin.com', 'iesdouyin.com'].some(domain => parsed.hostname === domain || parsed.hostname.endsWith(`.${domain}`))) return null;
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname.includes('.') || parsed.username || parsed.password) return null;
    return parsed.toString();
  } catch { return null; }
}

export function detectSourceFromUrl(value: string): Source | null {
  const url = normalizeContentUrl(value);
  if (!url) return null;
  const host = new URL(url).hostname.toLowerCase();
  return (Object.keys(SOURCE_META) as Source[]).find(source => SOURCE_META[source].domains.some(domain => host === domain || host.endsWith(`.${domain}`))) ?? 'other';
}
