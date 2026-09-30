import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/Layout';
import AdminLayout from './components/AdminLayout';
import Home from './features/articles/pages/Home';
import Articles from './features/articles/pages/Articles';
import Article from './features/articles/pages/Article';
import Admin from './features/tasks/pages/Admin';
import AdminTasks from './features/tasks/pages/AdminTasks';
import AdminArticles from './features/tasks/pages/AdminArticles';
import AdminSettings from './features/tasks/pages/AdminSettings';
import AdminModelSettings from './features/tasks/pages/AdminModelSettings';
import AdminTikHubSettings from './features/tasks/pages/AdminTikHubSettings';
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
          <Route path="article/:id" element={<Article />} />
          <Route path="share" element={<ShareReceive />} />
        </Route>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Admin />} />
          <Route path="tasks" element={<AdminTasks />} />
          <Route path="articles" element={<AdminArticles />} />
          <Route path="settings" element={<AdminSettings />} />
          <Route path="settings/model" element={<AdminModelSettings />} />
          <Route path="settings/tikhub" element={<AdminTikHubSettings />} />
          <Route path="settings/share" element={<ShareSetup />} />
          <Route path="tikhub/query" element={<AdminTikHubQuery />} />
        </Route>
        <Route path="share/setup" element={<Navigate to="/admin/settings/share" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
