import { FormEvent, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Check, Moon, Search, Sun } from 'lucide-react';
import { useAppStore } from '../features/app/store/useAppStore';
import { applyTheme, getTheme, THEMES } from '../features/app/themes';
import ToastStack from './ToastStack';

/** 品牌标:双色纸带 S(绿带 + 墨带,深色下墨带自动变暖纸白)。与 /favicon.svg 同形。 */
export function BrandMark({ size = 26, accent, ink }: { size?: number; accent?: string; ink?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path
        d="M23 11 C23 7.8 20.2 6.5 16 6.5 C11.8 6.5 9 7.8 9 11 C9 14.2 11.8 16.2 16.5 16.6"
        stroke={accent ?? 'var(--accent)'}
        strokeWidth="5.4"
        strokeLinecap="round"
      />
      <path
        d="M9 21 C9 24.2 11.8 25.5 16 25.5 C20.2 25.5 23 24.2 23 21 C23 17.8 20.2 15.8 15.5 15.4"
        stroke={ink ?? 'var(--ink)'}
        strokeWidth="5.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 前台(公开页面)布局:顶部菜单栏。后台控制台使用独立的 AdminLayout。 */
export default function Layout() {
  const { theme, setTheme } = useAppStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [searchValue, setSearchValue] = useState(searchParams.get('q') || '');
  const [themeOpen, setThemeOpen] = useState(false);
  const themePickerRef = useRef<HTMLDivElement>(null);

  // 挂载与切换时把主题落到 <html>,同时兜底:从后台返回时恢复前台主题(后台明暗独立)
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (!themeOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (themePickerRef.current && !themePickerRef.current.contains(event.target as Node)) {
        setThemeOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setThemeOpen(false); };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [themeOpen]);

  useEffect(() => {
    setSearchValue(searchParams.get('q') || '');
  }, [searchParams]);

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchValue.trim();
    navigate(query ? `/articles?q=${encodeURIComponent(query)}` : '/articles');
  };

  const handleSearchInputChange = (value: string) => {
    setSearchValue(value);
    // 输入框已清空而列表还筛着旧词,看起来像「搜索失效」:清空即恢复未筛选列表
    if (!value.trim() && location.pathname === '/articles' && searchParams.get('q')) {
      navigate('/articles', { replace: true });
    }
  };

  const currentTheme = getTheme(theme);

  return (
    <div className="site-frame">
      <header className="site-header">
        <div className="site-header-inner">
          <Link to="/" className="brand-mark" aria-label="SynthAI 首页">
            <BrandMark />
            <span>SynthAI</span>
          </Link>
          <nav className="public-nav" aria-label="主导航">
            <Link to="/" className={location.pathname === '/' ? 'active' : ''}>首页</Link>
            <Link to="/articles" className={location.pathname.startsWith('/article') ? 'active' : ''}>文章库</Link>
          </nav>
          <div className="header-actions">
            <form className={`header-search ${location.pathname === '/articles' ? 'library-header-search' : ''}`} onSubmit={handleSearch} role="search">
              <input
                value={searchValue}
                onChange={(event) => handleSearchInputChange(event.target.value)}
                onKeyDown={(event) => {
                  // Enter 默认的隐式提交在部分内嵌 webview 不生效:显式补一次,常规浏览器
                  // 走 preventDefault 后 requestSubmit 同样只触发一次 submit,不会重复导航
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="搜索文章"
                aria-label="搜索文章"
              />
              <button type="submit" className="search-submit" aria-label="提交搜索">
                <Search size={15} />
              </button>
            </form>
            <div className="theme-picker" ref={themePickerRef}>
              <button
                type="button"
                className="icon-button"
                onClick={() => setThemeOpen((open) => !open)}
                aria-label="选择主题"
                aria-haspopup="menu"
                aria-expanded={themeOpen}
              >
                {currentTheme.dark ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              {themeOpen && (
                <div className="theme-menu" role="menu" aria-label="主题">
                  <div className="theme-menu-title">主题</div>
                  {THEMES.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={item.id === theme}
                      className={item.id === theme ? 'theme-option active' : 'theme-option'}
                      onClick={() => { setTheme(item.id); setThemeOpen(false); }}
                    >
                      <span
                        className="theme-swatch"
                        style={{ '--sw-paper': item.swatch.paper, '--sw-accent': item.swatch.accent } as CSSProperties}
                        aria-hidden="true"
                      />
                      <span className="theme-option-name">{item.name}</span>
                      <span className="theme-option-hint">{item.hint}</span>
                      {item.id === theme && <Check size={14} />}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <span className="header-divider" aria-hidden="true" />
            <Link to="/admin" className="header-admin-link">管理后台 <ArrowUpRight size={13} /></Link>
          </div>
        </div>
      </header>

      <main className={`site-main ${location.pathname.startsWith('/article/') ? 'reader-site-main' : ''}`}>
        <Outlet />
      </main>

      <footer className="site-footer">
        <strong>© {new Date().getFullYear()} SynthAI</strong>
        <span>把值得读的内容，留在自己的知识库里。</span>
      </footer>

      <ToastStack />
    </div>
  );
}
