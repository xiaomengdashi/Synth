import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Check, Palette } from 'lucide-react';
import { ADMIN_THEMES } from '../features/app/adminThemes';
import { useAppStore } from '../features/app/store/useAppStore';

const THEME_MODES = [
  { id: 'light', label: '浅色' },
  { id: 'dark', label: '深色' },
  { id: 'system', label: '跟随系统' },
] as const;

export default function AdminThemeControl() {
  const { adminTheme, adminThemeMode, setAdminTheme, setAdminThemeMode } = useAppStore();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const currentTheme = ADMIN_THEMES.find((theme) => theme.id === adminTheme) ?? ADMIN_THEMES[0];

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="ac-theme-control" ref={rootRef}>
      <button
        type="button"
        className="ac-icon-btn ac-theme-trigger"
        onClick={() => setOpen((value) => !value)}
        aria-label="选择后台主题"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="后台主题"
      >
        <Palette size={17} />
        <span className="ac-theme-trigger-dot" style={{ background: `linear-gradient(135deg,${currentTheme.swatch.light} 0 50%,${currentTheme.swatch.dark} 50% 100%)` }} />
      </button>
      {open && (
        <section className="ac-theme-popover" role="dialog" aria-label="后台主题设置">
          <header className="ac-theme-popover-heading">
            <strong>后台主题</strong>
            <span>仅影响管理后台</span>
          </header>
          <div className="ac-theme-mode" role="group" aria-label="外观模式">
            {THEME_MODES.map((mode) => (
              <button
                key={mode.id}
                type="button"
                aria-pressed={adminThemeMode === mode.id}
                className={adminThemeMode === mode.id ? 'active' : ''}
                onClick={() => setAdminThemeMode(mode.id)}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <div className="ac-theme-list" role="group" aria-label="配色主题">
            {ADMIN_THEMES.map((theme) => (
              <button
                key={theme.id}
                type="button"
                aria-pressed={adminTheme === theme.id}
                className={adminTheme === theme.id ? 'ac-theme-option active' : 'ac-theme-option'}
                onClick={() => setAdminTheme(theme.id)}
              >
                <span
                  className="ac-theme-swatch"
                  style={{ '--admin-swatch-light': theme.swatch.light, '--admin-swatch-dark': theme.swatch.dark } as CSSProperties}
                  aria-hidden="true"
                />
                <span className="ac-theme-option-copy">
                  <strong>{theme.name}</strong>
                  <small>{theme.hint}</small>
                </span>
                {adminTheme === theme.id && <Check size={15} aria-hidden="true" />}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
