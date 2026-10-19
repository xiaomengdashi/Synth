import { useEffect, useState } from 'react';
import {
  Activity,
  BookOpenText,
  ChevronRight,
  Cpu,
  LayoutDashboard,
  Menu,
  MessagesSquare,
  Newspaper,
  X,
} from 'lucide-react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAppStore } from '../features/app/store/useAppStore';
import { BrandMark } from './Layout';
import AdminThemeControl from './AdminThemeControl';
import ToastStack from './ToastStack';
import AdminGate from './AdminGate';
import AdminSidebarNavigation from './AdminSidebarNavigation';

const NAV_GROUPS = [
  { path: '/admin', label: '总览', icon: LayoutDashboard },
  { path: '/admin/ask', label: '知识库问答', icon: MessagesSquare },
  { path: '/admin/articles', label: '内容管理', icon: Newspaper },
  { path: '/admin/tasks', label: '导入与任务', icon: Activity },
  { path: '/admin/tikhub', label: '系统设置', icon: Cpu },
];
const SECTIONS = [
  { label: '内容管理', items: [{ path: '/admin/articles', label: '文章管理' }, { path: '/admin/notes', label: '划线笔记' }, { path: '/admin/categories', label: '文章分类' }] },
  { label: '导入与任务', items: [{ path: '/admin/tasks', label: '处理任务' }, { path: '/admin/email', label: '邮箱导入' }, { path: '/admin/share', label: '手机分享导入' }] },
  { label: '系统设置', items: [{ path: '/admin/tikhub', label: '内容获取' }, { path: '/admin/model', label: '模型服务' }, { path: '/admin/token', label: '访问令牌' }] },
];

export default function AdminLayout() {
  const { adminTheme, adminThemeMode } = useAppStore();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  // 后台配色和外观模式独立于前台主题。
  useEffect(() => {
    const root = document.documentElement;
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    const applyMode = () => {
      const dark = adminThemeMode === 'dark' || (adminThemeMode === 'system' && systemTheme.matches);
      root.classList.toggle('dark', dark);
    };

    root.dataset.adminTheme = adminTheme;
    applyMode();
    if (adminThemeMode === 'system') systemTheme.addEventListener('change', applyMode);

    return () => {
      systemTheme.removeEventListener('change', applyMode);
      delete root.dataset.adminTheme;
    };
  }, [adminTheme, adminThemeMode]);

  // 路由变化时收起移动端抽屉
  useEffect(() => { setNavOpen(false); }, [location.pathname, location.search]);

  useEffect(() => {
    if (!navOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setNavOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navOpen]);

  const section = SECTIONS.find(group => group.items.some(item => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)));
  const isSettings = section?.label === '系统设置';
  const currentPage = section?.items.find(item => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`));
  const pageTitle = currentPage?.label ?? (location.pathname === '/admin/ask' ? '知识库问答' : location.pathname === '/admin' ? '总览' : undefined);
  // The top bar shows ancestors; the current page has one heading in the content area.
  const breadcrumbs = [
    { label: '后台管理', to: '/admin' },
    ...(section ? [{ label: section.label, to: section.items[0].path }] : []),
  ];

  return (
    <AdminGate>
    <div className={`admin-console${isSettings ? ' settings-console' : ''}${navOpen ? ' nav-open' : ''}`}>
      <aside className="ac-sidebar" aria-label="后台侧边栏">
        <Link to="/admin" className="ac-brand">
          <span className="ac-brand-logo"><BrandMark size={26} accent="var(--ac-accent)" ink="var(--ac-side-ink-strong)" /></span>
          <span className="ac-brand-text">
            <span className="ac-brand-name">SynthAI 控制台</span>
          </span>
        </Link>

        <AdminSidebarNavigation groups={NAV_GROUPS} sections={SECTIONS} />

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
          <nav className="ac-crumbs" aria-label="上级导航">
            {breadcrumbs.map((crumb, index) => (
              <span className="ac-crumb" key={crumb.label}>
                {index > 0 && <span className="ac-crumb-sep"><ChevronRight size={13} /></span>}
                <Link to={crumb.to}>{crumb.label}</Link>
              </span>
            ))}
          </nav>
          <div className="ac-topbar-spacer" />
          <AdminThemeControl />
        </header>

        <main className={isSettings ? 'ac-main system-settings' : 'ac-main'}>
          {pageTitle && !isSettings ? <header className="ac-workspace-heading"><h1>{pageTitle}</h1></header> : null}
          <Outlet />
        </main>
      </div>

      <ToastStack />
    </div>
    </AdminGate>
  );
}
