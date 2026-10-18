import { useEffect, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { activeSettingsItem } from '../settingsNavigation';

type SettingsSection = { id: string; label: string; content: ReactNode };

/** Load a section on its first visit, then retain its form and draft between visits. */
export default function SettingsWorkspace({ sections }: { sections: SettingsSection[] }) {
  const location = useLocation();
  const active = activeSettingsItem(location.pathname, location.search)?.id ?? sections[0].id;
  const [visited, setVisited] = useState(() => new Set([active]));

  useEffect(() => {
    setVisited(current => current.has(active) ? current : new Set([...current, active]));
  }, [active]);

  return (
    <div className="settings-panels">
      {sections.map(section => (
        <section key={section.id} aria-label={section.label} hidden={active !== section.id} className="settings-panel">
          {active === section.id || visited.has(section.id) ? section.content : null}
        </section>
      ))}
    </div>
  );
}
