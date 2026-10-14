import { useEffect, useState } from 'react';
import {
  Activity,
  BookOpenText,
  ChevronRight,
  Cpu,
  LayoutDashboard,
  Menu,
  Moon,
  Newspaper,
  Sun,
  X,
} from 'lucide-react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAppStore } from '../features/app/store/useAppStore';
import { BrandMark } from './Layout';
import ToastStack from './ToastStack';
import AdminGate from './AdminGate';

const NAV_GROUPS = [
  { path: '/admin', label: '工作台', icon: LayoutDashboard },
  { path: '/admin/articles', label: '内容管理', icon: Newspaper },
  { path: '/admin/tasks', label: '导入与任务', icon: Activity },
  { path: '/admin/tikhub', label: '系统设置', icon: Cpu },
];
const SECTIONS = [
  { label: '内容管理', items: [{ path: '/admin/articles', label: '文章管理' }, { path: '/admin/notes', label: '划线笔记' }, { path: '/admin/categories', label: '文章分类' }] },
  { label: '导入与任务', items: [{ path: '/admin/tasks', label: '处理任务' }, { path: '/admin/email', label: '邮箱导入' }, { path: '/admin/share', label: '手机分享导入' }] },
  { label: '系统设置', items: [{ path: '/admin/tikhub', label: 'TikHub 数据服务' }, { path: '/admin/model', label: '模型服务' }, { path: '/admin/token', label: '访问令牌' }] },
];

/** 面包屑:上级可点击跳转,最后一级是当前位置。 */
function useAdminBreadcrumbs(pathname: string) {
  if (pathname === '/admin/tasks') {
    return [{ label: '后台管理', to: '/admin' }, { label: '处理任务' }];
  }
  if (pathname === '/admin/articles') {
    return [{ label: '后台管理', to: '/admin' }, { label: '文章管理' }];
  }
  if (pathname === '/admin/notes') {
    return [{ label: '后台管理', to: '/admin' }, { label: '划线笔记' }];
  }
  if (pathname === '/admin/categories') {
    return [{ label: '后台管理', to: '/admin' }, { label: '文章分类' }];
  }
  if (pathname === '/admin/model') {
    return [{ label: '后台管理', to: '/admin' }, { label: '模型服务' }];
  }
  if (pathname === '/admin/email') {
    return [{ label: '后台管理', to: '/admin' }, { label: '邮箱导入' }];
  }
  if (pathname === '/admin/share') {
    return [{ label: '后台管理', to: '/admin' }, { label: '手机分享导入' }];
  }
  if (pathname === '/admin/token') {
    return [{ label: '后台管理', to: '/admin' }, { label: '访问令牌' }];
  }
  if (pathname.startsWith('/admin/tikhub') || pathname.startsWith('/admin/tikhub')) {
    return [{ label: '后台管理', to: '/admin' }, { label: 'TikHub 数据服务' }];
  }
  return [{ label: '后台管理', to: '/admin' }, { label: '工作台' }];
}

export default function AdminLayout() {
  const { adminDark, toggleAdminDark } = useAppStore();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const breadcrumbs = useAdminBreadcrumbs(location.pathname);
  // 后台明暗独立于前台主题:进入后台按自己的记录落 dark 类
  useEffect(() => {
    document.documentElement.classList.toggle('dark', adminDark);
  }, [adminDark]);

  // 路由变化时收起移动端抽屉
  useEffect(() => { setNavOpen(false); }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setNavOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navOpen]);

  const section = SECTIONS.find(group => group.items.some(item => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)));
  const isNavActive = (path: string) => {
    if (path === '/admin') return location.pathname === '/admin';
    return SECTIONS.find(group => group.items[0].path === path) === section;
  };

  return (
    <AdminGate>
    <div className={navOpen ? 'admin-console nav-open' : 'admin-console'}>
      <aside className="ac-sidebar" aria-label="后台侧边栏">
        <Link to="/admin" className="ac-brand">
          <span className="ac-brand-logo"><BrandMark size={26} accent="var(--ac-accent)" ink="var(--ac-side-ink-strong)" /></span>
          <span className="ac-brand-text">
            <span className="ac-brand-name">SynthAI 控制台</span>
          </span>
        </Link>

        <nav className="ac-nav" aria-label="后台导航">
          <div className="ac-nav-label">工作空间</div>
          {NAV_GROUPS.map(item => <Link to={item.path} key={item.path} className={isNavActive(item.path) ? 'ac-nav-item active' : 'ac-nav-item'} aria-current={isNavActive(item.path) ? 'page' : undefined}><item.icon size={18} /><span>{item.label}</span></Link>)}

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
          <button type="button" className="ac-icon-btn" onClick={toggleAdminDark} aria-label="切换明暗">
            {adminDark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </header>

        <main className="ac-main">
          {section ? <>
            <header className="ac-workspace-heading"><p className="eyebrow">SynthAI 控制台</p><h1>{section.label}</h1></header>
            <nav className="ac-section-nav" aria-label={`${section.label}页面`}>
              {section.items.map(item => <Link key={item.path} to={item.path} className={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`) ? 'active' : ''} aria-current={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`) ? 'page' : undefined}>{item.label}</Link>)}
            </nav>
          </> : null}
          <Outlet />
        </main>
      </div>

      <ToastStack />
    </div>
    </AdminGate>
  );
}
