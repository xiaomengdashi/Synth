import { create } from 'zustand';

export interface Article {
  id: string;
  title: string;
  summary: string;
  content_md: string;
  original_url: string;
  source_type: 'wechat' | 'bilibili' | 'douyin' | 'x' | 'csdn' | 'cnblogs' | 'other';
  cover_image_url?: string;
  created_at: string;
}

export interface Task {
  id: string;
  original_url: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  current_step: string;
  article_id?: string;
  created_at: string;
}

export interface AppConfig {
  modelName: string;
  apiKey: string;
  baseUrl: string;
  biliSessdata?: string;
  biliJct?: string;
  biliBuvid3?: string;
}

interface AppState {
  articles: Article[];
  tasks: Task[];
  darkMode: boolean;
  config: AppConfig;
  toggleDarkMode: () => void;
  addArticle: (article: Article) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  setConfig: (config: AppConfig) => void;
  fetchConfig: () => Promise<void>;
  fetchArticles: () => Promise<void>;
  deleteArticle: (articleId: string) => Promise<void>;
}

const mockArticles: Article[] = [
  {
    id: '1',
    title: 'DeepSeek-V3 核心原理解析：MoE与MLA架构的完美结合',
    summary: '本文深度剖析了DeepSeek-V3背后的技术创新，包括多专家混合模型（MoE）的调度策略以及多头潜在注意力机制（MLA）带来的推理性能飞跃。',
    content_md: '# DeepSeek-V3 核心原理解析\n\nDeepSeek-V3 采用了革命性的 **MoE** (Mixture of Experts) 架构与 **MLA** (Multi-head Latent Attention) 机制。\n\n## 1. MoE 架构优势\n\nMoE 通过动态路由激活部分网络参数，实现了在不增加推理成本的情况下大幅扩充模型容量。\n\n```python\ndef route_tokens(x, experts):\n    # 计算路由概率\n    probs = softmax(router(x))\n    # 选择 Top-K 专家\n    top_k = topk(probs, k=2)\n    return sum([experts[i](x) * probs[i] for i in top_k])\n```\n\n## 2. MLA 的突破\n\n传统的 Multi-head Attention 在 KV Cache 显存占用上是一个瓶颈。MLA 通过潜在向量映射，将 KV Cache 压缩了 4 倍，极大提升了长文本推理的吞吐量。\n\n> "这是自 Flash Attention 以来最优雅的工程创新。" —— AI 评论员',
    original_url: 'https://mp.weixin.qq.com/s/example',
    source_type: 'wechat',
    cover_image_url: 'https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt=Cyberpunk%20style%20neural%20network%20glowing%20nodes%20abstract%20technology%20blue%20neon&image_size=landscape_16_9',
    created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
  },
  {
    id: '2',
    title: 'Sora 发布最新更新，视频生成长度翻倍！',
    summary: 'OpenAI 刚刚更新了 Sora 视频生成模型，现在支持长达 2 分钟的高清视频生成，物理世界一致性得到了进一步改善。',
    content_md: '# Sora 最新更新\n\nOpenAI 震撼发布了 Sora 的 V1.5 版本更新，主要亮点包括：\n\n- **时长翻倍**：现在支持生成 120 秒视频\n- **一致性增强**：修复了此前多视角切换时的物体变形问题\n- **音频生成**：原生支持生成与画面同步的音效\n\n![Sora Demo](https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt=A%20futuristic%20camera%20lens%20floating%20in%20space%20capturing%20holographic%20video%20frames%20purple%20and%20cyan%20lighting&image_size=landscape_16_9)',
    original_url: 'https://www.bilibili.com/video/BV1xx411c7mD',
    source_type: 'bilibili',
    cover_image_url: 'https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt=A%20futuristic%20camera%20lens%20floating%20in%20space%20capturing%20holographic%20video%20frames%20purple%20and%20cyan%20lighting&image_size=landscape_16_9',
    created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
  },
  {
    id: '3',
    title: '如何用 LLM 构建全自动 AI 资讯网站',
    summary: '作者分享了自己使用 Next.js, FastAPI, FFmpeg 和 Whisper 搭建全自动 AI 资讯聚合站的全过程。',
    content_md: '# 构建全自动 AI 资讯站\n\n今天我们将探讨如何构建一个像 **SynthAI** 一样的全自动资讯聚合网站。\n\n## 架构概览\n\n1. **前端**：React / Next.js\n2. **后端**：Python FastAPI\n3. **爬虫**：BeautifulSoup + yt-dlp\n4. **AI 引擎**：Whisper (ASR) + GPT-4 (总结) + DALL-E 3 (配图)\n\n## 核心流程\n\n当我们输入一个 B站 链接时，系统会自动下载视频，提取音频，使用 Whisper 转写为文本，最后让大模型总结出核心 Markdown 文章。',
    original_url: 'https://twitter.com/example/status/123',
    source_type: 'x',
    cover_image_url: 'https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt=A%20complex%20server%20rack%20with%20glowing%20data%20streams%20connecting%20to%20a%20holographic%20brain%20green%20and%20blue&image_size=landscape_16_9',
    created_at: new Date(Date.now() - 3600000 * 48).toISOString(),
  }
];

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

export const useStore = create<AppState>((set, get) => ({
  articles: mockArticles,
  tasks: [],
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
    // 避免重复添加，并处理状态更新覆盖
    const exists = state.articles.find(a => a.id === article.id);
    if (exists) return state;
    return { articles: [article, ...state.articles] };
  }),
  addTask: (task) => set((state) => ({ tasks: [task, ...state.tasks] })),
  updateTask: (id, updates) => set((state) => ({
    tasks: state.tasks.map((t) => t.id === id ? { ...t, ...updates } : t)
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
      if (res.ok) {
        const data = await res.json();
        // 将获取到的文章与本地可能存在的mock文章合并去重（或者直接覆盖）
        if (data.data && Array.isArray(data.data)) {
          set((state) => {
            const newArticles = [...data.data];
            // 保留不冲突的 mock 数据（如果有的话，方便预览）
            state.articles.forEach(mockArt => {
              if (!newArticles.find(a => a.id === mockArt.id)) {
                newArticles.push(mockArt);
              }
            });
            // 排序，最新在上面
            newArticles.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
            return { articles: newArticles };
          });
        }
      }
    } catch (e) {
      console.error('Failed to fetch articles', e);
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
          tasks: state.tasks.filter((t) => t.article_id !== articleId)
        }));
      } else {
        console.error('Failed to delete article');
      }
    } catch (error) {
      console.error('Failed to delete article', error);
    }
  }
}));