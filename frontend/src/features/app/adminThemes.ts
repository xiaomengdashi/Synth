export type AdminThemeId = 'qwenpaw' | 'codex' | 'ayu' | 'catppuccin' | 'dracula' | 'everforest';
export type AdminThemeMode = 'light' | 'dark' | 'system';

export interface AdminThemePreset {
  id: AdminThemeId;
  name: string;
  hint: string;
  swatch: { light: string; dark: string };
}

export const ADMIN_THEMES: readonly AdminThemePreset[] = [
  { id: 'qwenpaw', name: 'QwenPaw', hint: '暖橙', swatch: { light: '#ff7f16', dark: '#ff9d4d' } },
  { id: 'codex', name: 'Codex', hint: '蓝色', swatch: { light: '#2563eb', dark: '#60a5fa' } },
  { id: 'ayu', name: 'Ayu', hint: '琥珀', swatch: { light: '#c56a00', dark: '#ffb454' } },
  { id: 'catppuccin', name: 'Catppuccin', hint: '紫罗兰', swatch: { light: '#7c3aed', dark: '#c4a7e7' } },
  { id: 'dracula', name: 'Dracula', hint: '玫粉', swatch: { light: '#c0268f', dark: '#ff79c6' } },
  { id: 'everforest', name: 'Everforest', hint: '森林绿', swatch: { light: '#2f7d4b', dark: '#a7c080' } },
];

export const DEFAULT_ADMIN_THEME: AdminThemeId = 'qwenpaw';

export const isAdminThemeId = (value: string): value is AdminThemeId =>
  ADMIN_THEMES.some((theme) => theme.id === value);

export const isAdminThemeMode = (value: string): value is AdminThemeMode =>
  value === 'light' || value === 'dark' || value === 'system';
