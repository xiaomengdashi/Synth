import { useEffect } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { useStore } from '../store/useStore';
import { Sun, Moon, Sparkles, LayoutDashboard, Home, Search } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function Layout() {
  const { darkMode, toggleDarkMode } = useStore();
  const location = useLocation();

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  const navItems = [
    { path: '/', label: '首页', icon: Home },
    { path: '/admin', label: '控制台', icon: LayoutDashboard },
  ];

  return (
    <div className="min-h-screen flex flex-col font-sans transition-colors duration-300 relative overflow-hidden">
      {/* Animated Background Mesh */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-40 mix-blend-screen dark:opacity-60 transition-opacity duration-700">
        <div className="absolute inset-0 bg-mesh dark:bg-mesh-dark"></div>
        {/* Floating orbs */}
        <div className="absolute top-[20%] left-[10%] w-[30rem] h-[30rem] bg-primary/20 dark:bg-primary/10 rounded-full blur-[100px] animate-float"></div>
        <div className="absolute bottom-[10%] right-[20%] w-[25rem] h-[25rem] bg-secondary/20 dark:bg-secondary/10 rounded-full blur-[80px] animate-float" style={{ animationDelay: '2s' }}></div>
      </div>

      {/* Navigation */}
      <nav className="sticky top-0 z-50 glass-panel border-x-0 border-t-0 rounded-none h-16 flex items-center justify-between px-6 lg:px-12 transition-all duration-300">
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary shadow-lg overflow-hidden group-hover:animate-glow">
              <Sparkles className="w-5 h-5 text-white" />
              <div className="absolute inset-0 bg-white/20 blur-md group-hover:opacity-100 opacity-0 transition-opacity"></div>
            </div>
            <span className="font-bold text-xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-300">
              SynthAI
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-1 bg-slate-100/50 dark:bg-slate-800/50 p-1 rounded-full border border-slate-200/50 dark:border-slate-700/50 backdrop-blur-sm">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  "flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-300",
                  location.pathname === item.path
                    ? "bg-white dark:bg-slate-700 text-primary shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-white/50 dark:hover:bg-slate-700/50"
                )}
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex relative group">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-primary transition-colors" />
            <input 
              type="text" 
              placeholder="搜索 AI 资讯..." 
              className="pl-9 pr-4 py-1.5 w-48 focus:w-64 transition-all duration-300 bg-slate-100/50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 dark:focus:ring-primary/30 text-slate-900 dark:text-slate-100 placeholder:text-slate-400"
            />
          </div>
          
          <button
            onClick={toggleDarkMode}
            className="p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-primary/50"
            aria-label="Toggle dark mode"
          >
            {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 relative z-10 container mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full max-w-7xl">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="relative z-10 glass-panel border-x-0 border-b-0 rounded-none py-6 mt-auto">
        <div className="container mx-auto px-6 text-center text-sm text-slate-500 dark:text-slate-400">
          <p>© {new Date().getFullYear()} SynthAI. Automated AI News Aggregator.</p>
        </div>
      </footer>
    </div>
  );
}