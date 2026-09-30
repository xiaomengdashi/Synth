import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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

function App() {
  const fetchArticles = useAppStore((state) => state.fetchArticles);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="articles" element={<Articles />} />
          <Route path="categories" element={<Categories />} />
          <Route path="article/:id" element={<Article />} />
          <Route path="share" element={<ShareReceive />} />
        </Route>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Admin />} />
          <Route path="tasks" element={<AdminTasks />} />
          <Route path="articles" element={<AdminArticles />} />
          <Route path="categories" element={<AdminCategories />} />
          <Route path="settings" element={<Navigate to="/admin/settings/tikhub" replace />} />
          <Route path="settings/model" element={<AdminModelSettings />} />
          <Route path="settings/tikhub" element={<AdminTikHubSettings />} />
          <Route path="settings/share" element={<ShareSetup />} />
          <Route path="settings/token" element={<AdminTokenSettings />} />
          <Route path="tikhub/query" element={<AdminTikHubQuery />} />
        </Route>
        <Route path="share/setup" element={<Navigate to="/admin/settings/share" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
