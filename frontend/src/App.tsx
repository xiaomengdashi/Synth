import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/Layout';
import AdminLayout from './components/AdminLayout';
import Home from './features/articles/pages/Home';
import Articles from './features/articles/pages/Articles';
import Categories from './features/articles/pages/Categories';
import Article from './features/articles/pages/Article';
import Admin from './features/tasks/pages/Admin';
import AdminTasks from './features/tasks/pages/AdminTasks';
import AdminArticles from './features/tasks/pages/AdminArticles';
import AdminCategories from './features/tasks/pages/AdminCategories';
import AdminModelSettings from './features/tasks/pages/AdminModelSettings';
import AdminTikHubSettings from './features/tasks/pages/AdminTikHubSettings';
import AdminTokenSettings from './features/tasks/pages/AdminTokenSettings';
import AdminTikHubQuery from './features/tikhub/AdminTikHubQuery';
import ShareReceive from './features/sharing/ShareReceive';
import ShareSetup from './features/sharing/ShareSetup';
import { useAppStore } from './features/app/store/useAppStore';
import ErrorBoundary from './components/ErrorBoundary';
import NotFound from './components/NotFound';

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
            <Route index element={<Home />} />
            <Route path="articles" element={<Articles />} />
            <Route path="categories" element={<Categories />} />
            <Route path="article/:id" element={<Article />} />
            <Route path="share" element={<ShareReceive />} />
            <Route path="*" element={<NotFound />} />
          </Route>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Admin />} />
            <Route path="tasks" element={<AdminTasks />} />
            <Route path="articles" element={<AdminArticles />} />
            <Route path="categories" element={<AdminCategories />} />
            <Route path="model" element={<AdminModelSettings />} />
            <Route path="tikhub" element={<AdminTikHubSettings />} />
            <Route path="share" element={<ShareSetup />} />
            <Route path="token" element={<AdminTokenSettings />} />
            <Route path="tikhub/query" element={<AdminTikHubQuery />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}

export default App;
