import { FormEvent, useEffect, useState } from 'react';
import { Outlet, Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  ArrowUpRight,
  BookOpenText,
  CheckCircle2,
  CircleHelp,
  FileText,
  LayoutDashboard,
  Moon,
  Newspaper,
  Search,
  Settings2,
  Sparkles,
  Sun,
  X,
  AlertCircle,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '../features/app/store/useAppStore';

function ToastItem({
  id,
  title,
  tone,
}: {
  id: string;
  title: string;
  tone: 'success' | 'error';
}) {
  const removeToast = useAppStore((state) => state.removeToast);

  useEffect(() => {
    const timer = window.setTimeout(() => removeToast(id), 2600);
    return () => window.clearTimeout(timer);
  }, [id, removeToast]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.98 }}
      className="toast-item"
    >
      <span className={tone === 'success' ? 'toast-icon success' : 'toast-icon error'}>
        {tone === 'success' ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
      </span>
      <span>{title}</span>
      <button type="button" onClick={() => removeToast(id)} aria-label="关闭提示">
        <X size={15} />
      </button>
    </motion.div>
  );
}

export default function Layout() {
  const { darkMode, toggleDarkMode, toasts } = useAppStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [searchValue, setSearchValue] = useState(searchParams.get('q') || '');
  const isAdmin = location.pathname.startsWith('/admin');
  const adminPageTitle = location.pathname === '/admin/tasks'
    ? '处理任务'
    : location.pathname === '/admin/articles'
      ? '文章管理'
      : location.pathname.startsWith('/admin/settings')
        ? '系统配置'
        : '内容总览';

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  useEffect(() => {
    setSearchValue(searchParams.get('q') || '');
  }, [searchParams]);

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchValue.trim();
    navigate(query ? `/articles?q=${encodeURIComponent(query)}` : '/articles');
  };

  const adminLinks = [
    { path: '/admin', label: '总览', icon: LayoutDashboard },
    { path: '/admin/articles', label: '文章库', icon: Newspaper },
    { path: '/admin/tasks', label: '处理任务', icon: Activity },
    { path: '/admin/settings', label: '系统配置', icon: Settings2 },
  ];

  return (
    <div className={isAdmin ? 'site-frame admin-frame' : 'site-frame'}>
      {isAdmin ? (
        <aside className="admin-sidebar">
          <Link to="/" className="brand-mark">
            <span className="brand-symbol"><Sparkles size={16} /></span>
            <span>Synth<span>AI</span></span>
          </Link>

          <div className="sidebar-label">工作台</div>
          <nav className="sidebar-nav" aria-label="后台导航">
            {adminLinks.map((item, index) => (
              <Link
                to={item.path}
                key={item.path}
                className={location.pathname === item.path || (item.path === '/admin/settings' && location.pathname.startsWith('/admin/settings/')) ? 'active' : ''}
              >
                <item.icon size={17} />
                <span>{item.label}</span>
                {index === 0 && <span className="nav-live-dot" />}
              </Link>
            ))}
          </nav>

          <div className="sidebar-spacer" />
          <div className="sidebar-help">
            <CircleHelp size={17} />
            <div>
              <strong>需要帮助？</strong>
              <span>查看导入指南</span>
            </div>
            <ArrowUpRight size={15} />
          </div>
          <Link to="/" className="back-to-site"><BookOpenText size={16} /> 返回前台</Link>
        </aside>
      ) : null}

      <div className="site-content">
        <header className={isAdmin ? 'site-header admin-header' : 'site-header'}>
          <div className="mobile-brand">
            <Link to="/" className="brand-mark">
              <span className="brand-symbol"><Sparkles size={15} /></span>
              <span>Synth<span>AI</span></span>
            </Link>
          </div>
          {!isAdmin ? (
            <nav className="public-nav" aria-label="主导航">
              <Link to="/" className={location.pathname === '/' ? 'active' : ''}>发现</Link>
              <Link to="/articles" className={location.pathname === '/articles' ? 'active' : ''}>文章库</Link>
            </nav>
          ) : (
            <div className="admin-breadcrumb"><span>后台管理</span><span>/</span><strong>{adminPageTitle}</strong></div>
          )}
          <div className="header-actions">
            <form className="header-search" onSubmit={handleSearch}>
              <input
                value={searchValue}
                onChange={(event) => setSearchValue(event.target.value)}
                placeholder="搜索文章或链接"
                aria-label="搜索文章或链接"
              />
              <button type="submit" className="search-submit" aria-label="提交搜索">
                <Search size={16} />
              </button>
            </form>
            <button type="button" className="icon-button" onClick={toggleDarkMode} aria-label="切换主题">
              {darkMode ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            {!isAdmin && <Link to="/admin" className="header-admin-link">管理后台 <ArrowUpRight size={14} /></Link>}
          </div>
        </header>

        <main className={isAdmin ? 'site-main admin-main' : 'site-main'}>
          <Outlet />
        </main>

        {!isAdmin && (
          <footer className="site-footer">
            <span>© {new Date().getFullYear()} SynthAI</span>
            <span>把值得读的内容，留在自己的知识库里。</span>
          </footer>
        )}
      </div>

      <div className="toast-stack">
        <AnimatePresence>
          {toasts.map((toast) => <ToastItem key={toast.id} {...toast} />)}
        </AnimatePresence>
      </div>
    </div>
  );
}
