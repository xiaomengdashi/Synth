import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, Bird, CheckCircle2, Cpu, KeyRound, RefreshCw, Smartphone, Wallet } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import { dateTime, money, requestJson } from '../../tikhub/client';
import type { Account, KeyStatus } from '../../tikhub/types';
import type { AppConfig } from '../../config/types';

type TabId = 'tikhub' | 'model' | 'share';

const TABS: { id: TabId; label: string; hint: string; icon: typeof Bird }[] = [
  { id: 'tikhub', label: 'TikHub 数据服务', hint: '数据抓取 · 必填', icon: Bird },
  { id: 'model', label: '模型服务', hint: 'AI 模型 · 未启用', icon: Cpu },
  { id: 'share', label: '手机分享导入', hint: '移动端 · 可选', icon: Smartphone },
];

function TikHubPanel() {
  const fetchConfig = useAppStore(state => state.fetchConfig);
  const [apiKey, setApiKey] = useState('');
  const [key, setKey] = useState<KeyStatus | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [accountError, setAccountError] = useState('');
  const [notice, setNotice] = useState('');
  const requestVersion = useRef(0);

  const loadAccount = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setAccountError('');
    try {
      const data = await requestJson<Account>('/api/v1/tikhub/account');
      if (version === requestVersion.current) setAccount(data);
    } catch (e) {
      if (version === requestVersion.current) {
        setAccount(null);
        setAccountError(e instanceof Error ? e.message : '账户信息查询失败');
      }
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const versionRef = requestVersion;
    void requestJson<KeyStatus>('/api/v1/tikhub/key').then(data => { if (active) setKey(data); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : '配置读取失败'); });
    void loadAccount();
    return () => { active = false; versionRef.current++; };
  }, [loadAccount]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!apiKey.trim()) { setError('请填写 API Key。'); return; }
    setSaving(true); setError(''); setNotice('');
    try {
      const data = await requestJson<KeyStatus>('/api/v1/tikhub/key', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKey: apiKey.trim() }),
      });
      setKey(data); setApiKey(''); setAccount(null);
      setNotice('Key 验证通过并已保存。');
      await fetchConfig();
      await loadAccount();
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  };

  const remove = async () => {
    setSaving(true); setError(''); setNotice('');
    try {
      const data = await requestJson<KeyStatus>('/api/v1/tikhub/key', { method: 'DELETE' });
      setKey(data); setAccount(null); setApiKey('');
      setNotice('已移除保存的 Key，抓取功能将不可用，重新保存即可恢复。');
      await fetchConfig();
      await loadAccount();
    } catch (e) { setError(e instanceof Error ? e.message : '移除失败'); }
    finally { setSaving(false); }
  };

  const usage = account?.daily_usage;
  const counts = Object.entries(usage?.uri_counts || {}).sort((a, b) => b[1] - a[1]);
  const user = account?.user;
  const api = account?.api_key;

  return (
    <div className="settings-tab-panel">
      <section className="settings-panel settings-form-panel">
        <h2><KeyRound size={16} /> API Key 设置</h2>
        <p>在 <a href="https://user.tikhub.io" target="_blank" rel="noreferrer">TikHub 控制台</a> 创建 Key。验证通过后保存，验证失败时现有 Key 保持不变。</p>
        <div className="tikhub-key-status">
          <span className={key?.configured ? 'config-status ready' : 'config-status'}>
            {key === null ? '读取配置中' : key.configured ? '已配置' : '尚未配置'}
          </span>
          {key?.configured && <><code>{key.masked_key}</code><span>Key 仅保存在服务端数据库</span></>}
        </div>
        <form onSubmit={save}>
          <div className="form-field">
            <label htmlFor="tikhub-key">TikHub API Key</label>
            <input id="tikhub-key" type="password" autoComplete="new-password" spellCheck={false} value={apiKey}
              onChange={event => setApiKey(event.target.value)} maxLength={4096} disabled={saving}
              placeholder={key?.configured ? '输入新 Key 以更换' : '粘贴 TikHub API Key'} />
            <p className="form-help">Key 仅保存在后端数据库，不会回传到浏览器。</p>
          </div>
          {error && <p className="tikhub-message error" role="alert">{error}</p>}
          {notice && <p className="tikhub-message success" role="status">{notice}</p>}
          <div className="modal-footer">
            {key?.has_saved_key && <button type="button" className="secondary-button" onClick={() => void remove()} disabled={saving}>移除已保存 Key</button>}
            <button type="submit" className="primary-button" disabled={saving || !apiKey.trim()}>{saving ? '正在处理…' : '验证并保存'}</button>
          </div>
        </form>
      </section>

      <section className="settings-panel tikhub-account" aria-busy={loading}>
        <div className="tikhub-section-heading"><h2><Wallet size={16} /> 账户与今日用量</h2>
          <button type="button" className="secondary-button" onClick={() => void loadAccount()} disabled={loading || saving}><RefreshCw size={14} />{loading ? '查询中…' : '刷新账户'}</button>
        </div>
        {loading ? <p className="tikhub-empty" role="status">正在查询 TikHub 账户…</p>
          : accountError ? <p className="tikhub-message error" role="alert">{accountError}</p>
          : !account?.configured ? <p className="tikhub-empty">保存 Key 后可查看余额、权限和每日调用明细。</p>
          : user && <>
            <div className="tikhub-metrics">
              <div><span>账户余额</span><strong>{money(user.balance)}</strong></div>
              <div><span>免费额度</span><strong>{money(user.free_credit)}</strong></div>
              <div><span>今日花费</span><strong>{money(usage?.usage, 4)}</strong></div>
              <div><span>今日请求 / 付费请求</span><strong>{usage?.total_request_per_day ?? '—'} <small>/ {usage?.paid_request_per_day ?? '—'}</small></strong></div>
            </div>
            <dl className="tikhub-details">
              <div><dt>账户邮箱</dt><dd>{user.email || '—'}</dd></div>
              <div><dt>账户状态</dt><dd>{user.is_active && !user.account_disabled ? '正常' : '未激活或已禁用'}</dd></div>
              <div><dt>Key 名称</dt><dd>{api?.name || '—'}</dd></div>
              <div><dt>Key 状态</dt><dd>{api?.status === 1 ? '已启用' : api?.status === 0 ? '已禁用' : `状态 ${api?.status ?? '未知'}`}</dd></div>
              <div><dt>创建时间</dt><dd>{dateTime(api?.created_at)}</dd></div>
              <div><dt>到期时间</dt><dd>{api?.expires_at ? dateTime(api.expires_at) : '未设置到期时间'}</dd></div>
            </dl>
            {!!api?.scopes?.length && <details className="tikhub-disclosure"><summary>查看 Key 权限（{api.scopes_count} 项）</summary><ul>{api.scopes.map(scope => <li key={scope}><code>{scope}</code></li>)}</ul></details>}
            {account.warnings?.map(warning => <p className="tikhub-message warning" role="status" key={warning}>{warning}</p>)}
            {usage && <div className="tikhub-usage">
              <h3>接口调用明细 <small>{usage.date || '日期由 TikHub 返回'}</small></h3>
              {counts.length ? <div className="tikhub-table-scroll"><table><thead><tr><th>接口</th><th>请求次数</th></tr></thead><tbody>{counts.map(([path, count]) => <tr key={path}><td><code>{path}</code></td><td>{count}</td></tr>)}</tbody></table></div>
                : <p className="form-help">本日暂无接口调用明细。</p>}
            </div>}
            <p className="form-help">更新时间：{dateTime(account.updated_at)} · 用量日期及统计时区以 TikHub 返回为准。</p>
          </>}
      </section>

      <section className="settings-panel">
        <div className="tikhub-section-heading"><h2><Bird size={16} /> 多平台数据查询</h2></div>
        <p>按平台浏览 TikHub 接口目录，查询内容详情、用户信息、评论或搜索数据；查询按官方计费消耗额度。</p>
        <div className="modal-footer">
          <Link to="/admin/tikhub/query" className="secondary-button">进入多平台查询 <ArrowRight size={14} /></Link>
        </div>
      </section>
    </div>
  );
}

function ModelPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState<AppConfig>(config);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const displayKey = (key: string) => key.length > 6 ? `${key.slice(0, 4)}...${key.slice(-2)}` : key;
  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setConfig({ ...localConfig, apiKey: localConfig.apiKey.includes('...') ? config.apiKey : localConfig.apiKey });
  };

  return (
    <div className="settings-tab-panel">
      <form className="settings-panel settings-form-panel" onSubmit={save}>
        <h2><Cpu size={16} /> 连接参数</h2>
        <p>OpenAI 兼容服务的参数在模型服务商控制台获取。当前内容导入不调用模型，参数留作后续功能启用。</p>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="base-url">Base URL</label>
            <input id="base-url" type="url" value={localConfig.baseUrl} onChange={(event) => setLocalConfig({ ...localConfig, baseUrl: event.target.value })} placeholder="https://api.openai.com/v1" />
          </div>
          <div className="form-field">
            <label htmlFor="api-key">API Key</label>
            <input id="api-key" type="text" value={localConfig.apiKey === config.apiKey && config.apiKey ? displayKey(config.apiKey) : localConfig.apiKey} onFocus={() => { if (localConfig.apiKey === config.apiKey) setLocalConfig({ ...localConfig, apiKey: '' }); }} onChange={(event) => setLocalConfig({ ...localConfig, apiKey: event.target.value })} placeholder="sk-..." />
          </div>
          <div className="form-field full">
            <label htmlFor="model-name">模型名称</label>
            <input id="model-name" value={localConfig.modelName} onChange={(event) => setLocalConfig({ ...localConfig, modelName: event.target.value })} placeholder="gpt-4o-mini / deepseek-chat" />
          </div>
        </div>
        <div className="modal-footer">
          <button type="submit" className="primary-button">保存模型配置</button>
        </div>
      </form>
    </div>
  );
}

function SharePanel() {
  return (
    <div className="settings-tab-panel">
      <section className="settings-panel settings-form-panel">
        <h2><Smartphone size={16} /> iPhone 分享导入</h2>
        <p>安装「保存到 SynthAI」快捷指令后，在手机上的 X 或微信里看到好文章，直接从分享菜单保存进文章库，无需打开电脑。</p>
        <div className="share-flow"><span>分享菜单</span><ArrowRight size={15} /><span>保存到 SynthAI</span><ArrowRight size={15} /><span>文章库</span></div>
        <p className="form-help">完整设置（网站地址确认、iCloud 一键安装、手动创建指引）在独立页面完成。</p>
        <div className="modal-footer">
          <Link to="/admin/settings/share" className="primary-button">打开分享设置 <ArrowRight size={14} /></Link>
        </div>
      </section>
    </div>
  );
}

export default function AdminSettings() {
  const { config, fetchConfig } = useAppStore();
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab') as TabId | null;
  const tab: TabId = TABS.some(t => t.id === tabParam) ? (tabParam as TabId) : 'tikhub';

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);

  const modelReady = Boolean(config.baseUrl || config.modelName || config.apiKey);
  const tikhubReady = Boolean(config.tikhubConfigured);
  const statuses: Record<TabId, { ready: boolean; text: string }> = {
    tikhub: { ready: tikhubReady, text: tikhubReady ? '已配置' : '未配置' },
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
          {tab === 'tikhub' && <TikHubPanel />}
          {tab === 'model' && <ModelPanel />}
          {tab === 'share' && <SharePanel />}
        </div>
      </div>
    </div>
  );
}
