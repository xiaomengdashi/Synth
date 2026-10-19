import { Suspense, lazy, useEffect, useLayoutEffect, useRef, type ComponentType } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigationType } from 'react-router-dom';
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
const AdminNotes = lazyPage(() => import('./features/tasks/pages/AdminNotes'));
const AdminKnowledge = lazyPage(() => import('./features/knowledge/pages/AdminKnowledge'));
const AdminCategories = lazyPage(() => import('./features/tasks/pages/AdminCategories'));
const AdminModelSettings = lazyPage(() => import('./features/tasks/pages/AdminModelSettings'));
const AdminEmailImport = lazyPage(() => import('./features/email/pages/AdminEmailImport'));
const AdminTikHubSettings = lazyPage(() => import('./features/tasks/pages/AdminTikHubSettings'));
const AdminTokenSettings = lazyPage(() => import('./features/tasks/pages/AdminTokenSettings'));
const AdminTikHubQuery = lazyPage(() => import('./features/tikhub/AdminTikHubQuery'));
const ShareReceive = lazyPage(() => import('./features/sharing/ShareReceive'));
const ShareSetup = lazyPage(() => import('./features/sharing/ShareSetup'));

function PageLoading() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '50vh', color: 'var(--muted, #5e5a4f)' }}>
      <Loader2 size={22} className="animate-spin" />
    </div>
  );
}

/** 路由滚动管理:点进新页面回顶;浏览器后退回到离开时的位置。
 * 不做这层,SPA 切页会继承上一页的滚动深度(分类页落在文章库滚到一半的位置),
 * 从列表点进文章再返回又要从头滚起。 */
const PROGRAMMATIC_SCROLL_SUPPRESS_MS = 80;

function ScrollManager() {
  const location = useLocation();
  const action = useNavigationType();
  // scrollTo 是程序性滚动,触发的 scroll 事件可能赶在旧路由的保存监听卸载之前
  // 到达,把 0 写进旧页面的保存记录(后退恢复失效);窗口期内一律不保存
  const suppressSaveUntilRef = useRef(0);

  useLayoutEffect(() => {
    const key = location.key || 'root';
    const saved = action === 'POP' ? sessionStorage.getItem(`synthai-scroll:${key}`) : null;
    suppressSaveUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_SUPPRESS_MS;
    window.scrollTo({ top: saved ? Number(saved) || 0 : 0, behavior: 'instant' });
  }, [location.key, action]);

  useEffect(() => {
    const key = location.key || 'root';
    const onScroll = () => {
      if (Date.now() < suppressSaveUntilRef.current) return;
      sessionStorage.setItem(`synthai-scroll:${key}`, String(Math.round(window.scrollY)));
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [location.key]);

  return null;
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
      <ScrollManager />
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
            <Route path="notes" element={<Suspense fallback={<PageLoading />}><AdminNotes /></Suspense>} />
            <Route path="ask" element={<Suspense fallback={<PageLoading />}><AdminKnowledge /></Suspense>} />
            <Route path="categories" element={<Suspense fallback={<PageLoading />}><AdminCategories /></Suspense>} />
            <Route path="model" element={<Suspense fallback={<PageLoading />}><AdminModelSettings /></Suspense>} />
            <Route path="email" element={<Suspense fallback={<PageLoading />}><AdminEmailImport /></Suspense>} />
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
