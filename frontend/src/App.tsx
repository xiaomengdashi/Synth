import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/Layout';
import Home from './features/articles/pages/Home';
import Articles from './features/articles/pages/Articles';
import Article from './features/articles/pages/Article';
import Admin from './features/tasks/pages/Admin';
import AdminTasks from './features/tasks/pages/AdminTasks';
import AdminArticles from './features/tasks/pages/AdminArticles';
import AdminSettings from './features/tasks/pages/AdminSettings';
import AdminModelSettings from './features/tasks/pages/AdminModelSettings';
import AdminBilibiliSettings from './features/tasks/pages/AdminBilibiliSettings';
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
          <Route path="article/:id" element={<Article />} />
          <Route path="share" element={<ShareReceive />} />
          <Route path="share/setup" element={<ShareSetup />} />
          <Route path="admin" element={<Admin />} />
          <Route path="admin/tasks" element={<AdminTasks />} />
          <Route path="admin/articles" element={<AdminArticles />} />
          <Route path="admin/settings" element={<AdminSettings />} />
          <Route path="admin/settings/model" element={<AdminModelSettings />} />
          <Route path="admin/settings/bilibili" element={<AdminBilibiliSettings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
