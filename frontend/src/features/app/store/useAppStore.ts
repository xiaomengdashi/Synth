import { create } from 'zustand';
import type { Article } from '../../articles/types';
import type { AppConfig } from '../../config/types';
import type { Task } from '../../tasks/types';

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
  setConfig: (config: AppConfig) => void;
  fetchConfig: () => Promise<void>;
  fetchArticles: () => Promise<void>;
  fetchTasks: () => Promise<void>;
  deleteArticle: (articleId: string) => Promise<boolean>;
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

export const useAppStore = create<AppState>((set) => ({
  articles: [],
  tasks: [],
  toasts: [],
  darkMode: initialDarkMode,
  config: {
    modelName: 'gpt-4o-mini',
    apiKey: '',
    baseUrl: 'https://api.openai.com/v1',
    biliSessdata: '',
    biliJct: '',
    biliBuvid3: '',
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
  removeToast: (toastId) => set((state) => ({
    toasts: state.toasts.filter((toast) => toast.id !== toastId)
  })),
  setConfig: async (config) => {
    set(() => ({ config }));
    try {
      await fetch('/api/v1/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
    } catch (e) {
      console.error('Failed to save config', e);
    }
  },
  fetchConfig: async () => {
    try {
      const res = await fetch('/api/v1/config');
      if (res.ok) {
        const data = await res.json();
        if (data.apiKey || data.baseUrl) {
          set((state) => ({ config: { ...state.config, ...data } }));
        }
      }
    } catch (e) {
      console.error('Failed to fetch config', e);
    }
  },
  fetchArticles: async () => {
    try {
      const res = await fetch('/api/v1/articles');
      if (!res.ok) throw new Error(`Articles API returned ${res.status}`);
      const data = await res.json();
      if (!data.data || !Array.isArray(data.data)) throw new Error('Articles API returned an invalid payload');
      const nextArticles = [...data.data];
      nextArticles.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      set(() => ({ articles: nextArticles }));
    } catch (e) {
      console.error('Failed to fetch articles', e);
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
