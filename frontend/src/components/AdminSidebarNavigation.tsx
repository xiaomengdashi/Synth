import { useId, useLayoutEffect, useState } from 'react';
import { ChevronDown, type LucideIcon } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { activeSettingsItem, SETTINGS_GROUPS } from '../features/tasks/settingsNavigation';

type NavigationGroup = { path: string; label: string; icon: LucideIcon };
type NavigationSection = { label: string; items: { path: string; label: string }[] };

export default function AdminSidebarNavigation({ groups, sections }: { groups: NavigationGroup[]; sections: NavigationSection[] }) {
  const { pathname, search } = useLocation();
  const id = useId();
  const activeSection = sections.find(section => section.items.some(item => pathname === item.path || pathname.startsWith(`${item.path}/`)));
  const activePath = activeSection?.items[0].path ?? null;
  const currentSetting = activeSettingsItem(pathname, search);
  const [expandedPaths, setExpandedPaths] = useState<string[]>(activePath ? [activePath] : []);

  // Reveal the current page while preserving other groups the user has opened.
  useLayoutEffect(() => {
    if (activePath) setExpandedPaths(current => current.includes(activePath) ? current : [...current, activePath]);
  }, [activePath, pathname, search]);

  return (
    <nav className="ac-nav ac-accordion-nav" aria-label="后台导航">
      {groups.map((group, index) => {
        const section = sections.find(section => section.items[0].path === group.path);
        if (!section) return (
          <Link key={group.path} to={group.path} className={`ac-nav-item${pathname === group.path ? ' active' : ''}`} aria-current={pathname === group.path ? 'page' : undefined}>
            <group.icon size={20} strokeWidth={1.7} /><span>{group.label}</span>
          </Link>
        );
        const open = expandedPaths.includes(group.path);
        const links = section.label === '系统设置'
          ? SETTINGS_GROUPS.flatMap(settingsGroup => settingsGroup.items.map(item => ({
            key: item.id, label: item.label,
            to: item.id === 'query' ? item.path : `${item.path}?section=${item.id}`,
            active: currentSetting?.id === item.id,
          })))
          : section.items.map(item => ({ key: item.path, label: item.label, to: item.path, active: pathname === item.path }));
        const triggerId = `${id}-trigger-${index}`;
        const panelId = `${id}-panel-${index}`;
        return (
          <div className="ac-nav-accordion" key={group.path}>
            <button type="button" id={triggerId} className={`ac-nav-item ac-nav-toggle${activePath === group.path ? ' active' : ''}`}
              aria-expanded={open} aria-controls={panelId} onClick={() => setExpandedPaths(current =>
                current.includes(group.path) ? current.filter(path => path !== group.path) : [...current, group.path])}>
              <group.icon size={20} strokeWidth={1.7} /><span>{group.label}</span><ChevronDown size={16} className="ac-accordion-chevron" aria-hidden="true" />
            </button>
            <div id={panelId} role="group" aria-labelledby={triggerId} hidden={!open} className="ac-settings-menu ac-accordion-panel">
              {links.map(item => (
                <Link key={item.key} to={item.to} className={`ac-settings-link${item.active ? ' active' : ''}`}
                  aria-current={item.active ? 'page' : undefined}>{item.label}</Link>
              ))}
            </div>
          </div>
        );
      })}
    </nav>
  );
}
