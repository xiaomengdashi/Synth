import { FormEvent, useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Moon, Search, Sun } from 'lucide-react';
import { useAppStore } from '../features/app/store/useAppStore';
import ToastStack from './ToastStack';

/** 品牌标:双色纸带 S(绿带 + 墨带,深色下墨带自动变暖纸白)。与 /favicon.svg 同形。 */
export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path
        d="M23 11 C23 7.8 20.2 6.5 16 6.5 C11.8 6.5 9 7.8 9 11 C9 14.2 11.8 16.2 16.5 16.6"
        stroke="var(--accent)"
        strokeWidth="5.4"
        strokeLinecap="round"
      />
      <path
        d="M9 21 C9 24.2 11.8 25.5 16 25.5 C20.2 25.5 23 24.2 23 21 C23 17.8 20.2 15.8 15.5 15.4"
        stroke="var(--ink)"
        strokeWidth="5.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 前台(公开页面)布局:顶部菜单栏。后台控制台使用独立的 AdminLayout。 */
export default function Layout() {
  const { darkMode, toggleDarkMode } = useAppStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [searchValue, setSearchValue] = useState(searchParams.get('q') || '');

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

  return (
    <div className="site-frame">
      <header className="site-header">
        <div className="site-header-inner">
          <Link to="/" className="brand-mark" aria-label="SynthAI 首页">
            <BrandMark />
            <span>SynthAI</span>
          </Link>
          <nav className="public-nav" aria-label="主导航">
            <Link to="/" className={location.pathname === '/' ? 'active' : ''}>发现</Link>
            <Link to="/articles" className={location.pathname.startsWith('/article') ? 'active' : ''}>文章库</Link>
          </nav>
          <div className="header-actions">
            <form className="header-search" onSubmit={handleSearch} role="search">
              <input
                value={searchValue}
                onChange={(event) => setSearchValue(event.target.value)}
                placeholder="搜索文章"
                aria-label="搜索文章"
              />
              <button type="submit" className="search-submit" aria-label="提交搜索">
                <Search size={15} />
              </button>
            </form>
            <button type="button" className="icon-button" onClick={toggleDarkMode} aria-label="切换主题">
              {darkMode ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <Link to="/admin" className="header-admin-link">管理后台 <ArrowUpRight size={13} /></Link>
          </div>
        </div>
      </header>

      <main className="site-main">
        <Outlet />
      </main>

      <footer className="site-footer">
        <span>© {new Date().getFullYear()} SynthAI</span>
        <span>把值得读的内容，留在自己的知识库里。</span>
      </footer>

      <ToastStack />
    </div>
  );
}
