/**
 * 前台「纸墨书房」主题注册表。
 * 每个主题 = 一套 index.css 变量(纸面/墨色/强调色)+ 明暗属性;
 * 来源功能色(--wechat/--x-blue/--bili)不随主题变化。
 * 注意:index.html 头部的防闪烁脚本内联了同一份 id→明暗映射,两处需同步。
 */

export type ThemeId = 'zhimo' | 'qingci' | 'moye' | 'dianqing';

export interface ThemeMeta {
  id: ThemeId;
  name: string;
  hint: string;
  dark: boolean;
  /** 选择面板里的色板圆点:纸面底色 + 强调色 */
  swatch: { paper: string; accent: string };
}

export const THEMES: ThemeMeta[] = [
  { id: 'zhimo', name: '纸墨', hint: '松绿纸白', dark: false, swatch: { paper: '#f6f5f1', accent: '#175b41' } },
  { id: 'qingci', name: '青瓷', hint: '天青釉白', dark: false, swatch: { paper: '#f1f4f2', accent: '#2b8274' } },
  { id: 'moye', name: '墨夜', hint: '玄墨竹青', dark: true, swatch: { paper: '#1a1815', accent: '#6fbf8f' } },
  { id: 'dianqing', name: '靛青', hint: '靛夜月青', dark: true, swatch: { paper: '#12161f', accent: '#82aae0' } },
];

/** 已下线主题的旧值 → 最接近的保留主题,避免已选用户被重置到默认 */
export const LEGACY_THEME_MAP: Record<string, ThemeId> = {
  qiushi: 'zhimo',
  subai: 'zhimo',
  daizi: 'moye',
};

export const DEFAULT_THEME: ThemeId = 'moye';

export const isThemeId = (value: string): value is ThemeId =>
  THEMES.some((theme) => theme.id === value);

export const getTheme = (id: ThemeId): ThemeMeta =>
  THEMES.find((theme) => theme.id === id) ?? THEMES.find((theme) => theme.id === DEFAULT_THEME)!;

/** 把主题落到 <html> 上:dark 类供 Tailwind/后台/旧覆盖样式使用,data-theme 决定变量块 */
export function applyTheme(id: ThemeId): void {
  const meta = getTheme(id);
  document.documentElement.classList.toggle('dark', meta.dark);
  document.documentElement.dataset.theme = meta.id;
}
