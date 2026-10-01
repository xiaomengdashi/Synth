import { create } from 'zustand';
import type { Article } from '../../articles/types';
import type { AppConfig } from '../../config/types';
import type { Task } from '../../tasks/types';
import { adminFetch } from '../../../utils/adminAuth';

export interface ToastMessage {
  id: string;
  title: string;
  tone: 'success' | 'error';
}

interface AppState {
  articles: Article[];
  tasks: Task[];
  toasts: ToastMessage[];
  darkMode: boolean;
  config: AppConfig;
  toggleDarkMode: () => void;
  addArticle: (article: Article) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  pushToast: (toast: Omit<ToastMessage, 'id'>) => void;
  removeToast: (toastId: string) => void;
  setConfig: (config: AppConfig) => Promise<boolean>;
  fetchConfig: () => Promise<void>;
  fetchArticles: (options?: { reset?: boolean; all?: boolean }) => Promise<void>;
  articlesHasMore: boolean;
  articlesLoading: boolean;
  fetchTasks: () => Promise<void>;
  deleteArticle: (articleId: string) => Promise<boolean>;
  updateArticle: (articleId: string, patch: Partial<Article>) => void;
}

// 从 localStorage 获取初始主题设置
const getInitialDarkMode = () => {
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme !== null) {
    return savedTheme === 'dark';
  }
  // 默认暗色模式
  return true;
};

// 立即应用初始主题，防止页面闪烁
const initialDarkMode = getInitialDarkMode();
if (initialDarkMode) {
  document.documentElement.classList.add('dark');
} else {
  document.documentElement.classList.remove('dark');
}

export const useAppStore = create<AppState>((set, get) => ({
  articles: [],
  articlesHasMore: true,
  articlesLoading: false,
  tasks: [],
  toasts: [],
  darkMode: initialDarkMode,
  config: {
    modelName: 'gpt-4o-mini',
    apiKey: '',
    apiKeyConfigured: false,
    baseUrl: 'https://api.openai.com/v1',
    tikhubConfigured: false,
  },
  toggleDarkMode: () => set((state) => {
    const newDarkMode = !state.darkMode;
    if (newDarkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
    return { darkMode: newDarkMode };
  }),
  addArticle: (article) => set((state) => {
    const nextArticles = state.articles.filter((item) => item.id !== article.id);
    nextArticles.unshift(article);
    nextArticles.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return { articles: nextArticles };
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
        body: JSON.stringify({ apiKey: config.apiKey, baseUrl: config.baseUrl, modelName: config.modelName }),
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
  // 渐进加载:每次拉 5 篇元信息,滚动到底继续取下一页
  fetchArticles: async (options) => {
    const reset = options?.reset ?? false;
    const fetchAll = options?.all ?? false;
    const state = get();
    if (state.articlesLoading) return;
    if (!reset && !state.articlesHasMore) return;

    const pageSize = fetchAll ? 50 : 5;
    const offset = reset ? 0 : state.articles.length;
    set({ articlesLoading: true });
    try {
      const res = await fetch(`/api/v1/articles?limit=${pageSize}&offset=${offset}`);
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
      const res = await fetch(`/api/v1/articles/${articleId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        set((state) => ({
          articles: state.articles.filter((a) => a.id !== articleId),
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
  }
}));
