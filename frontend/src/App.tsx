import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import Layout from './components/Layout';
import AdminLayout from './components/AdminLayout';
import ErrorBoundary from './components/ErrorBoundary';
import NotFound from './components/NotFound';
import { useAppStore } from './features/app/store/useAppStore';

// 路由级代码分割:前台/后台/重依赖页面各自分包,首屏只加载当前路由需要的代码
const Home = lazy(() => import('./features/articles/pages/Home'));
const Articles = lazy(() => import('./features/articles/pages/Articles'));
const Categories = lazy(() => import('./features/articles/pages/Categories'));
const Article = lazy(() => import('./features/articles/pages/Article'));
const Admin = lazy(() => import('./features/tasks/pages/Admin'));
const AdminTasks = lazy(() => import('./features/tasks/pages/AdminTasks'));
const AdminArticles = lazy(() => import('./features/tasks/pages/AdminArticles'));
const AdminCategories = lazy(() => import('./features/tasks/pages/AdminCategories'));
const AdminModelSettings = lazy(() => import('./features/tasks/pages/AdminModelSettings'));
const AdminTikHubSettings = lazy(() => import('./features/tasks/pages/AdminTikHubSettings'));
const AdminTokenSettings = lazy(() => import('./features/tasks/pages/AdminTokenSettings'));
const AdminTikHubQuery = lazy(() => import('./features/tikhub/AdminTikHubQuery'));
const ShareReceive = lazy(() => import('./features/sharing/ShareReceive'));
const ShareSetup = lazy(() => import('./features/sharing/ShareSetup'));

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
