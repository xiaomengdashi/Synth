import { useEffect, useState } from 'react';
import { Bird, CheckCircle2, Cpu, Smartphone } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import SettingsTikHubPanel from '../components/SettingsTikHubPanel';
import SettingsModelPanel from '../components/SettingsModelPanel';
import SettingsSharePanel from '../components/SettingsSharePanel';
import { money, requestJson } from '../../tikhub/client';
import type { Account } from '../../tikhub/types';

type TabId = 'tikhub' | 'model' | 'share';

const TABS: { id: TabId; label: string; hint: string; icon: typeof Bird }[] = [
  { id: 'tikhub', label: 'TikHub 数据服务', hint: '数据抓取 · 必填', icon: Bird },
  { id: 'model', label: '模型服务', hint: 'AI 模型 · 未启用', icon: Cpu },
  { id: 'share', label: '手机分享导入', hint: '移动端 · 可选', icon: Smartphone },
];

export default function AdminSettings() {
  const { config, fetchConfig } = useAppStore();
  const [params, setParams] = useSearchParams();
  const [account, setAccount] = useState<Account | null>(null);
  const tabParam = params.get('tab') as TabId | null;
  const tab: TabId = TABS.some(t => t.id === tabParam) ? (tabParam as TabId) : 'tikhub';

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => {
    void requestJson<Account>('/api/v1/tikhub/account').then(setAccount).catch(() => setAccount(null));
  }, []);

  const modelReady = Boolean(config.baseUrl || config.modelName || config.apiKey);
  const tikhubReady = Boolean(config.tikhubConfigured);
  const statuses: Record<TabId, { ready: boolean; text: string }> = {
    tikhub: tikhubReady && account?.user
      ? { ready: true, text: `余额 ${money(account.user.balance)}` }
      : { ready: tikhubReady, text: tikhubReady ? '已配置' : '未配置' },
    model: { ready: modelReady, text: modelReady ? '参数已保存' : '未设置' },
    share: { ready: false, text: '可选功能' },
  };

  return (
    <div>
      <AdminPageHeader
        eyebrow="Settings / 04"
        title="系统配置"
        description="内容抓取依赖 TikHub 接口；模型服务与手机分享导入为可选功能。"
      />
      <div className="settings-shell">
        <nav className="settings-nav" aria-label="配置分区">
          {TABS.map(({ id, label, hint, icon: Icon }) => (
            <button
              type="button"
              key={id}
              className={id === tab ? 'settings-nav-item active' : 'settings-nav-item'}
              aria-current={id === tab ? 'page' : undefined}
              onClick={() => setParams(id === 'tikhub' ? {} : { tab: id }, { replace: true })}
            >
              <span className="settings-nav-icon"><Icon size={16} /></span>
              <span className="settings-nav-text">
                <strong>{label}</strong>
                <small>
                  {hint}
                  {statuses[id].ready && <CheckCircle2 size={12} className="settings-nav-check" />}
                </small>
              </span>
              {id === 'tikhub' && (
                <span className="settings-nav-meta">{statuses[id].text}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="settings-content">
          {tab === 'tikhub' && <SettingsTikHubPanel />}
          {tab === 'model' && <SettingsModelPanel />}
          {tab === 'share' && <SettingsSharePanel />}
        </div>
      </div>
    </div>
  );
}
