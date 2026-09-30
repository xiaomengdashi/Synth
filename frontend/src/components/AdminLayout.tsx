import { FormEvent, useEffect, useState } from 'react';
import {
  Activity,
  BookOpenText,
  ChevronRight,
  LayoutDashboard,
  Menu,
  Moon,
  Newspaper,
  Search,
  Settings2,
  Sun,
  Tags,
  X,
} from 'lucide-react';
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAppStore } from '../features/app/store/useAppStore';
import { BrandMark } from './Layout';
import ToastStack from './ToastStack';

const NAV_GROUPS: { label: string; items: { path: string; label: string; icon: typeof LayoutDashboard }[] }[] = [
  { label: '工作台', items: [{ path: '/admin', label: '总览', icon: LayoutDashboard }] },
  {
    label: '内容',
    items: [
      { path: '/admin/articles', label: '文章管理', icon: Newspaper },
      { path: '/admin/categories', label: '文章分类', icon: Tags },
      { path: '/admin/tasks', label: '处理任务', icon: Activity },
    ],
  },
  { label: '系统', items: [{ path: '/admin/settings', label: '系统配置', icon: Settings2 }] },
];

/** 面包屑:上级可点击跳转,最后一级是当前位置。层级严格跟随 URL(?tab= 才细化第三级)。 */
function useAdminBreadcrumbs(pathname: string, settingsTab: string | null) {
  const settingsTabLabel =
    settingsTab === 'model' ? '模型服务'
      : settingsTab === 'share' ? '手机分享导入'
        : settingsTab === 'tikhub' ? 'TikHub 数据服务'
          : null;
  if (pathname === '/admin/categories') {
    return [{ label: '后台管理', to: '/admin' }, { label: '文章分类' }];
  }
  if (pathname === '/admin/tasks') {
    return [{ label: '后台管理', to: '/admin' }, { label: '处理任务' }];
  }
  if (pathname === '/admin/articles') {
    return [{ label: '后台管理', to: '/admin' }, { label: '文章管理' }];
  }
  if (pathname.startsWith('/admin/tikhub')) {
    return [{ label: '后台管理', to: '/admin' }, { label: '系统配置', to: '/admin/settings' }, { label: '多平台查询' }];
  }
  if (pathname === '/admin/settings/share') {
    return [{ label: '后台管理', to: '/admin' }, { label: '系统配置', to: '/admin/settings' }, { label: '手机分享导入' }];
  }
  if (pathname.startsWith('/admin/settings')) {
    return settingsTabLabel
      ? [{ label: '后台管理', to: '/admin' }, { label: '系统配置', to: '/admin/settings' }, { label: settingsTabLabel }]
      : [{ label: '后台管理', to: '/admin' }, { label: '系统配置' }];
  }
  return [{ label: '后台管理', to: '/admin' }, { label: '总览' }];
}

export default function AdminLayout() {
  const { darkMode, toggleDarkMode } = useAppStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [searchValue, setSearchValue] = useState(searchParams.get('q') || '');
  const [navOpen, setNavOpen] = useState(false);
  const breadcrumbs = useAdminBreadcrumbs(location.pathname, searchParams.get('tab'));
  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  // 路由变化时收起移动端抽屉
  useEffect(() => { setNavOpen(false); }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setNavOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navOpen]);

  useEffect(() => {
    setSearchValue(searchParams.get('q') || '');
  }, [searchParams]);

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchValue.trim();
    navigate(query ? `/articles?q=${encodeURIComponent(query)}` : '/articles');
  };

  const isNavActive = (path: string) => {
    if (path === '/admin') return location.pathname === '/admin';
    if (path === '/admin/settings') {
      // 面包屑里「多平台查询」挂在系统配置之下,侧边栏保持一致的选中态
      return location.pathname.startsWith('/admin/settings') || location.pathname.startsWith('/admin/tikhub');
    }
    return location.pathname === path;
  };

  return (
    <div className={navOpen ? 'admin-console nav-open' : 'admin-console'}>
      <aside className="ac-sidebar" aria-label="后台侧边栏">
        <Link to="/admin" className="ac-brand">
          <span className="ac-brand-logo"><BrandMark size={26} accent="var(--ac-accent)" ink="var(--ac-side-ink-strong)" /></span>
          <span className="ac-brand-text">
            <span className="ac-brand-name">SynthAI 控制台</span>
          </span>
        </Link>

        <nav className="ac-nav" aria-label="后台导航">
          {NAV_GROUPS.map((group) => (
            <div className="ac-nav-group" key={group.label}>
              <div className="ac-nav-label">{group.label}</div>
              {group.items.map((item) => (
                <Link
                  to={item.path}
                  key={item.path}
                  className={isNavActive(item.path) ? 'ac-nav-item active' : 'ac-nav-item'}
                  aria-current={isNavActive(item.path) ? 'page' : undefined}
                >
                  <item.icon size={16} />
                  <span>{item.label}</span>
                </Link>
              ))}
            </div>
          ))}
        </nav>

        <div className="ac-side-foot">
          <Link to="/" className="ac-back-site"><BookOpenText size={15} /> 返回前台网站</Link>
        </div>
      </aside>

      <button type="button" className="ac-scrim" aria-label="关闭侧边栏" onClick={() => setNavOpen(false)} />

      <div className="ac-body">
        <header className="ac-topbar">
          <button type="button" className="ac-icon-btn ac-menu-btn" onClick={() => setNavOpen(true)} aria-label="打开侧边栏" aria-expanded={navOpen}>
            {navOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <Link to="/admin" className="ac-topbar-brand">SynthAI</Link>
          <nav className="ac-crumbs" aria-label="面包屑">
            {breadcrumbs.map((crumb, index) => (
              <span className="ac-crumb" key={crumb.label}>
                {index > 0 && <span className="ac-crumb-sep"><ChevronRight size={13} /></span>}
                {crumb.to && index < breadcrumbs.length - 1 ? (
                  <Link to={crumb.to}>{crumb.label}</Link>
                ) : (
                  <strong aria-current={index === breadcrumbs.length - 1 ? 'page' : undefined}>{crumb.label}</strong>
                )}
              </span>
            ))}
          </nav>
          <div className="ac-topbar-spacer" />
          <form className="ac-search" onSubmit={handleSearch}>
            <Search size={15} />
            <input
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder="搜索文章或链接"
              aria-label="搜索文章或链接"
            />
          </form>
          <button type="button" className="ac-icon-btn" onClick={toggleDarkMode} aria-label="切换主题">
            {darkMode ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </header>

        <main className="ac-main">
          <Outlet />
        </main>
      </div>

      <ToastStack />
    </div>
  );
}
