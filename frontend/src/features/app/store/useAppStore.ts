import { create } from 'zustand';
import type { Article } from '../../articles/types';
import type { AppConfig } from '../../config/types';
import type { Task } from '../../tasks/types';
import { adminFetch } from '../../../utils/adminAuth';
import { applyTheme, DEFAULT_THEME, isThemeId, type ThemeId } from '../themes';

export interface ToastMessage {
  id: string;
  title: string;
  tone: 'success' | 'error';
}

interface AppState {
  articles: Article[];
  tasks: Task[];
  toasts: ToastMessage[];
  theme: ThemeId;
  adminDark: boolean;
  config: AppConfig;
  setTheme: (id: ThemeId) => void;
  toggleAdminDark: () => void;
  addArticle: (article: Article) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  pushToast: (toast: Omit<ToastMessage, 'id'>) => void;
  removeToast: (toastId: string) => void;
  setConfig: (config: AppConfig) => Promise<boolean>;
  fetchConfig: () => Promise<void>;
  fetchArticles: (options?: { reset?: boolean; all?: boolean; category?: string; source?: string; q?: string }) => Promise<void>;
  articlesHasMore: boolean;
  articlesLoading: boolean;
  articlesTotal: number;
  fetchTasks: () => Promise<void>;
  deleteArticle: (articleId: string) => Promise<boolean>;
  batchDeleteArticles: (ids: string[]) => Promise<boolean>;
  batchSetCategory: (ids: string[], category: string) => Promise<boolean>;
  updateArticle: (articleId: string, patch: Partial<Article>) => void;
}

// 前台主题:localStorage 存主题 id;旧值 'dark'/'light' 迁移为墨夜/纸墨
const getInitialTheme = (): ThemeId => {
  const saved = localStorage.getItem('theme');
  if (saved && isThemeId(saved)) return saved;
  return saved === 'light' ? 'zhimo' : DEFAULT_THEME;
};

// 后台明暗独立于前台主题(后台是自己的设计系统,只有亮暗两态);
// 初次迁移时沿用旧的全局明暗记录,落定后存独立的 admin-dark
const getInitialAdminDark = (legacyTheme: string | null): boolean => {
  const saved = localStorage.getItem('admin-dark');
  if (saved !== null) return saved === 'dark';
  return legacyTheme !== 'light';
};

const savedThemeRaw = localStorage.getItem('theme');
const initialTheme = getInitialTheme();
const initialAdminDark = getInitialAdminDark(savedThemeRaw);
// 立即归一化存储:旧值/脏值换成主题 id,后台明暗落到独立键
if (savedThemeRaw !== initialTheme) {
  localStorage.setItem('theme', initialTheme);
}
if (localStorage.getItem('admin-dark') === null) {
  localStorage.setItem('admin-dark', initialAdminDark ? 'dark' : 'light');
}
// 立即应用初始主题，防止页面闪烁
applyTheme(initialTheme);

export const useAppStore = create<AppState>((set, get) => ({
  articles: [],
  articlesHasMore: true,
  articlesLoading: false,
  articlesTotal: 0,
  tasks: [],
  toasts: [],
  theme: initialTheme,
  adminDark: initialAdminDark,
  setTheme: (id) => {
    if (!isThemeId(id)) return;
    localStorage.setItem('theme', id);
    applyTheme(id);
    set({ theme: id });
  },
  toggleAdminDark: () => set((state) => {
    const adminDark = !state.adminDark;
    localStorage.setItem('admin-dark', adminDark ? 'dark' : 'light');
    return { adminDark };
  }),
  config: {
    modelName: 'gpt-4o-mini',
    apiKey: '',
    apiKeyConfigured: false,
    baseUrl: 'https://api.openai.com/v1',
    tikhubConfigured: false,
  },
  addArticle: (article) => set((state) => {
    const isNew = !state.articles.some((item) => item.id === article.id);
    const nextArticles = state.articles.filter((item) => item.id !== article.id);
    nextArticles.unshift(article);
    nextArticles.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return { articles: nextArticles, articlesTotal: isNew ? state.articlesTotal + 1 : state.articlesTotal };
  }),
  addTask: (task) => set((state) => ({ tasks: [task, ...state.tasks] })),
  updateTask: (id, updates) => set((state) => ({
    tasks: state.tasks.map((t) => t.id === id ? { ...t, ...updates } : t)
  })),
  pushToast: (toast) => set((state) => ({
    toasts: [...state.toasts, { ...toast, id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }]
  })),
  updateArticle: (articleId, patch) => set((state) => ({
    articles: state.articles.map((a) => (a.id === articleId ? { ...a, ...patch } : a)),
  })),
  removeToast: (toastId) => set((state) => ({
    toasts: state.toasts.filter((toast) => toast.id !== toastId)
  })),
  setConfig: async (config) => {
    try {
      const res = await adminFetch('/api/v1/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiKey: config.apiKey, baseUrl: config.baseUrl, modelName: config.modelName,
          minimaxApiKey: config.minimaxApiKey ?? '',
          imapHost: config.imapHost ?? '', imapUser: config.imapUser ?? '',
          imapPassword: config.imapPassword ?? '', imapSenderWhitelist: config.imapSenderWhitelist ?? '',
        }),
      });
      if (!res.ok) return false;
      const saved = await res.json();
      set((state) => ({ config: { ...state.config, ...saved } }));
      return true;
    } catch (e) {
      console.error('Failed to save config', e);
      return false;
    }
  },
  fetchConfig: async () => {
    try {
      const res = await fetch('/api/v1/config');
      if (res.ok) {
        const data = await res.json();
        if (data && typeof data === 'object') {
          set((state) => ({ config: { ...state.config, ...data } }));
        }
      }
    } catch (e) {
      console.error('Failed to fetch config', e);
    }
  },
  // 渐进加载:元信息每条仅百余字节,单页多取一些能显著减少滚动续载的请求次数;
  // 筛选/搜索由后端完成,滚动到底继续取下一页
  fetchArticles: async (options) => {
    const reset = options?.reset ?? false;
    const fetchAll = options?.all ?? false;
    const category = options?.category;
    const source = options?.source;
    const keyword = options?.q?.trim() ?? '';
    const state = get();
    if (state.articlesLoading) return;
    if (!reset && !state.articlesHasMore) return;

    const pageSize = fetchAll ? 50 : 20;
    const offset = reset ? 0 : state.articles.length;
    set({ articlesLoading: true });
    try {
      const catParam = category === '__none' ? '__none__' : category;
      const catQuery = catParam ? `&category=${encodeURIComponent(catParam)}` : '';
      const sourceQuery = source ? `&source=${encodeURIComponent(source)}` : '';
      const qQuery = keyword ? `&q=${encodeURIComponent(keyword)}` : '';
      const res = await fetch(`/api/v1/articles?limit=${pageSize}&offset=${offset}${catQuery}${sourceQuery}${qQuery}`);
      if (!res.ok) throw new Error(`Articles API returned ${res.status}`);
      const data = await res.json();
      if (!data.data || !Array.isArray(data.data)) throw new Error('Articles API returned an invalid payload');
      const page = data.data as Article[];
      set((current) => {
        const merged = reset
          ? page
          : [...current.articles, ...page.filter((item) => !current.articles.some((a) => a.id === item.id))];
        return {
          articles: merged,
          articlesHasMore: offset + page.length < data.total,
          articlesTotal: data.total,
          articlesLoading: false,
        };
      });
    } catch (e) {
      console.error('Failed to fetch articles', e);
      set({ articlesLoading: false });
    }
  },
  fetchTasks: async () => {
    try {
      const res = await fetch('/api/v1/tasks');
      if (!res.ok) throw new Error(`Tasks API returned ${res.status}`);
      const data = await res.json();
      if (!Array.isArray(data.data)) throw new Error('Tasks API returned an invalid payload');
      set(() => ({ tasks: data.data }));
    } catch (e) {
      console.error('Failed to fetch tasks', e);
    }
  },
  deleteArticle: async (articleId: string) => {
    try {
      const res = await adminFetch(`/api/v1/articles/${articleId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        set((state) => ({
          articles: state.articles.filter((a) => a.id !== articleId),
          articlesTotal: Math.max(0, state.articlesTotal - 1),
          tasks: state.tasks.filter((t) => t.article_id !== articleId),
          toasts: [...state.toasts, {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            title: '文章已删除',
            tone: 'success',
          }]
        }));
        return true;
      } else {
        console.error('Failed to delete article');
        set((state) => ({
          toasts: [...state.toasts, {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            title: '删除失败，请稍后重试',
            tone: 'error',
          }]
        }));
        return false;
      }
    } catch (error) {
      console.error('Failed to delete article', error);
      set((state) => ({
        toasts: [...state.toasts, {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          title: '删除失败，请稍后重试',
          tone: 'error',
        }]
      }));
      return false;
    }
  },
  // 批量操作:反馈(toast)由调用方统一给出,这里只改状态并返回成败
  batchDeleteArticles: async (ids) => {
    try {
      const res = await adminFetch('/api/v1/articles/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      if (!res.ok) return false;
      const removing = new Set(ids);
      set((state) => ({
        articles: state.articles.filter((a) => !removing.has(a.id)),
        articlesTotal: Math.max(0, state.articlesTotal - state.articles.filter((a) => removing.has(a.id)).length),
        tasks: state.tasks.filter((t) => !t.article_id || !removing.has(t.article_id)),
      }));
      return true;
    } catch (error) {
      console.error('Failed to batch delete articles', error);
      return false;
    }
  },
  batchSetCategory: async (ids, category) => {
    try {
      const res = await adminFetch('/api/v1/articles/batch-category', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, category }),
      });
      if (!res.ok) return false;
      const changing = new Set(ids);
      set((state) => ({
        articles: state.articles.map((a) => (changing.has(a.id) ? { ...a, category: category || null } : a)),
      }));
      return true;
    } catch (error) {
      console.error('Failed to batch set category', error);
      return false;
    }
  }
}));
