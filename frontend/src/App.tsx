import { Suspense, lazy, useEffect, type ComponentType } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import Layout from './components/Layout';
import AdminLayout from './components/AdminLayout';
import ErrorBoundary from './components/ErrorBoundary';
import NotFound from './components/NotFound';
import { useAppStore } from './features/app/store/useAppStore';

// 高 RTT/代理链路下大 chunk 下载中途失败并不罕见,而 import() 失败后浏览器不会自动恢复:
// 先静默重试一次,仍失败则由 ErrorBoundary 整页刷新兜底
function lazyPage(loader: () => Promise<{ default: ComponentType<unknown> }>) {
  return lazy(async () => {
    try {
      return await loader();
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 800));
      return loader();
    }
  });
}

// 路由级代码分割:前台/后台/重依赖页面各自分包,首屏只加载当前路由需要的代码
const Home = lazyPage(() => import('./features/articles/pages/Home'));
const Articles = lazyPage(() => import('./features/articles/pages/Articles'));
const Categories = lazyPage(() => import('./features/articles/pages/Categories'));
const Article = lazyPage(() => import('./features/articles/pages/Article'));
const Admin = lazyPage(() => import('./features/tasks/pages/Admin'));
const AdminTasks = lazyPage(() => import('./features/tasks/pages/AdminTasks'));
const AdminArticles = lazyPage(() => import('./features/tasks/pages/AdminArticles'));
const AdminCategories = lazyPage(() => import('./features/tasks/pages/AdminCategories'));
const AdminModelSettings = lazyPage(() => import('./features/tasks/pages/AdminModelSettings'));
const AdminTikHubSettings = lazyPage(() => import('./features/tasks/pages/AdminTikHubSettings'));
const AdminTokenSettings = lazyPage(() => import('./features/tasks/pages/AdminTokenSettings'));
const AdminTikHubQuery = lazyPage(() => import('./features/tikhub/AdminTikHubQuery'));
const ShareReceive = lazyPage(() => import('./features/sharing/ShareReceive'));
const ShareSetup = lazyPage(() => import('./features/sharing/ShareSetup'));

function PageLoading() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '50vh', color: 'var(--muted, #7d776b)' }}>
      <Loader2 size={22} className="animate-spin" />
    </div>
  );
}

function App() {
  const fetchArticles = useAppStore((state) => state.fetchArticles);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  useEffect(() => {
    // 部分 webview 渲染帧不推进,CSS 动画时钟停摆会让 fill-mode 永久停在首帧(opacity 0)。
    // 首屏 stagger 封顶 0.48s + 时长 0.3s,窗口期过后统一禁用进场动画,内容必然可见。
    const t = window.setTimeout(() => document.documentElement.classList.add('no-anim'), 1600);
    return () => window.clearTimeout(t);
  }, []);

  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Suspense fallback={<PageLoading />}><Home /></Suspense>} />
            <Route path="articles" element={<Suspense fallback={<PageLoading />}><Articles /></Suspense>} />
            <Route path="categories" element={<Suspense fallback={<PageLoading />}><Categories /></Suspense>} />
            <Route path="article/:id" element={<Suspense fallback={<PageLoading />}><Article /></Suspense>} />
            <Route path="share" element={<Suspense fallback={<PageLoading />}><ShareReceive /></Suspense>} />
            <Route path="*" element={<NotFound />} />
          </Route>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Suspense fallback={<PageLoading />}><Admin /></Suspense>} />
            <Route path="tasks" element={<Suspense fallback={<PageLoading />}><AdminTasks /></Suspense>} />
            <Route path="articles" element={<Suspense fallback={<PageLoading />}><AdminArticles /></Suspense>} />
            <Route path="categories" element={<Suspense fallback={<PageLoading />}><AdminCategories /></Suspense>} />
            <Route path="model" element={<Suspense fallback={<PageLoading />}><AdminModelSettings /></Suspense>} />
            <Route path="tikhub" element={<Suspense fallback={<PageLoading />}><AdminTikHubSettings /></Suspense>} />
            <Route path="share" element={<Suspense fallback={<PageLoading />}><ShareSetup /></Suspense>} />
            <Route path="token" element={<Suspense fallback={<PageLoading />}><AdminTokenSettings /></Suspense>} />
            <Route path="tikhub/query" element={<Suspense fallback={<PageLoading />}><AdminTikHubQuery /></Suspense>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}

export default App;
