import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Bird, Cpu, KeyRound, ListChecks, PlugZap, Plus, RefreshCw, Share2, Smartphone, Wallet } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { dateTime, money, requestJson } from '../../tikhub/client';
import type { Account, KeyStatus } from '../../tikhub/types';

type TabId = 'tikhub' | 'model' | 'share';

const TABS: { id: TabId; label: string }[] = [
  { id: 'tikhub', label: 'TikHub 数据服务' },
  { id: 'model', label: '模型服务' },
  { id: 'share', label: '手机分享导入' },
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
    <div className="ac-stack">
      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><KeyRound size={15} /> TikHub API Key
            <span className={key !== null && key.configured ? 'ac-badge success' : 'ac-badge pending'}>
              {key === null ? '读取中' : key.configured ? '已配置' : '尚未配置'}
            </span>
          </h2>
          <p>内容抓取依赖 TikHub 接口。在 <a href="https://user.tikhub.io" target="_blank" rel="noreferrer">TikHub 控制台</a> 创建 Key，验证通过后保存；验证失败时现有 Key 保持不变。</p>
          {key?.configured && <div className="tikhub-key-status"><code>{key.masked_key}</code><span>Key 仅保存在服务端数据库</span></div>}
        </div>
        <div className="ac-set-main">
          <form onSubmit={save}>
            <div className="ac-field">
              <label htmlFor="tikhub-key">粘贴新的 API Key</label>
              <input id="tikhub-key" className="ac-input" type="password" autoComplete="new-password" spellCheck={false} value={apiKey}
                onChange={event => setApiKey(event.target.value)} maxLength={4096} disabled={saving}
                placeholder={key?.configured ? '输入新 Key 以更换' : '粘贴 TikHub API Key'} />
              <p className="ac-help">Key 仅保存在后端数据库，不会回传到浏览器。</p>
            </div>
            {error && <p className="tikhub-message error" role="alert">{error}</p>}
            {notice && <p className="tikhub-message success" role="status">{notice}</p>}
            <div className="ac-actions">
              {key?.has_saved_key && <button type="button" className="ac-btn secondary" onClick={() => void remove()} disabled={saving}>移除已保存 Key</button>}
              <button type="submit" className="ac-btn primary" disabled={saving || !apiKey.trim()}>{saving ? '正在处理…' : '验证并保存'}</button>
            </div>
          </form>
        </div>
      </section>

      <section className="ac-set-card" aria-busy={loading}>
        <div className="ac-set-side">
          <h2><Wallet size={15} /> 账户与今日用量</h2>
          <p>余额、Key 权限与每日调用明细，数据来自 TikHub，按需刷新。</p>
          <button type="button" className="ac-btn secondary sm" onClick={() => void loadAccount()} disabled={loading || saving}><RefreshCw size={13} />{loading ? '查询中…' : '刷新账户'}</button>
        </div>
        <div className="ac-set-main">
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
                  : <p className="ac-help">本日暂无接口调用明细。</p>}
              </div>}
              <p className="ac-help">更新时间：{dateTime(account.updated_at)} · 用量日期及统计时区以 TikHub 返回为准。</p>
            </>}
        </div>
      </section>

      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><Bird size={15} /> 多平台数据查询</h2>
          <p>按平台浏览 TikHub 接口目录，查询内容详情、用户信息、评论或搜索数据；查询按官方计费消耗额度。</p>
        </div>
        <div className="ac-set-main">
          <Link to="/admin/tikhub/query" className="ac-btn primary">进入多平台查询 <ArrowRight size={14} /></Link>
        </div>
      </section>
    </div>
  );
}

function ModelPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [models, setModels] = useState<string[]>([]);
  const [listing, setListing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modelMessage, setModelMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  // 表单里的 Key 是掩码时不下发，后端改用已保存的真实 Key
  const effectiveApiKey = localConfig.apiKey.includes('•')
    ? undefined : (localConfig.apiKey.trim() || undefined);

  const persistConfig = () => setConfig(localConfig);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true); setModelMessage(null);
    const ok = await persistConfig();
    setModelMessage(ok
      ? { tone: 'success', text: '模型配置已保存。' }
      : { tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    setSaving(false);
  };

  const saveAndTest = async () => {
    setTesting(true); setModelMessage(null);
    const saved = await persistConfig();
    if (!saved) {
      setModelMessage({ tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
      setTesting(false);
      return;
    }
    try {
      const data = await requestJson<{ ok: boolean; latency_ms: number }>('/api/v1/models/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: localConfig.baseUrl, apiKey: effectiveApiKey, model: localConfig.modelName }),
      });
      setModelMessage({ tone: 'success', text: `配置已保存，模型「${localConfig.modelName}」连接成功，响应 ${data.latency_ms} ms。` });
    } catch (e) {
      setModelMessage({ tone: 'error', text: `配置已保存，但连接测试失败：${e instanceof Error ? e.message : '未知错误'}` });
    } finally { setTesting(false); }
  };

  const fetchModels = async () => {
    setListing(true); setModelMessage(null);
    try {
      const data = await requestJson<{ models: string[] }>('/api/v1/models/list', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: localConfig.baseUrl, apiKey: effectiveApiKey }),
      });
      setModels(data.models);
      if (!localConfig.modelName.trim() && data.models.length) {
        setLocalConfig((current) => ({ ...current, modelName: data.models[0] }));
      }
      setModelMessage({ tone: 'success', text: `获取到 ${data.models.length} 个可用模型，在「模型名称」中下拉选择。` });
    } catch (e) {
      setModelMessage({ tone: 'error', text: e instanceof Error ? e.message : '获取模型列表失败。' });
    } finally { setListing(false); }
  };

  return (
    <div className="ac-stack">
      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><Cpu size={15} /> 连接参数</h2>
          <p>OpenAI 兼容服务的参数在模型服务商控制台获取。当前内容导入不调用模型，参数留作后续功能启用。</p>
        </div>
        <div className="ac-set-main">
          <form onSubmit={save}>
            <div className="ac-field">
              <label htmlFor="base-url">Base URL</label>
              <input id="base-url" className="ac-input" type="url" value={localConfig.baseUrl} onChange={(event) => setLocalConfig({ ...localConfig, baseUrl: event.target.value })} placeholder="https://api.openai.com/v1" />
            </div>
            <div className="ac-field">
              <label htmlFor="model-api-key">API Key</label>
              <input id="model-api-key" className="ac-input" type="password" autoComplete="new-password" value={localConfig.apiKey} onChange={(event) => setLocalConfig({ ...localConfig, apiKey: event.target.value })} placeholder={config.apiKeyConfigured ? '已配置，输入新 Key 可更换' : 'sk-...'} />
              <p className="ac-help">Key 仅保存在后端数据库；页面读取时只返回掩码。</p>
            </div>
            <div className="ac-field">
              <label htmlFor="model-name">模型名称</label>
              <div className="ac-input-group">
                <input id="model-name" className="ac-input" list="model-name-options" value={localConfig.modelName} onChange={(event) => { setLocalConfig({ ...localConfig, modelName: event.target.value }); setModelMessage(null); }} placeholder="gpt-4o-mini / deepseek-chat" disabled={listing} />
                <button type="button" className="ac-btn secondary" onClick={() => void fetchModels()} disabled={listing}>
                  <ListChecks size={14} />{listing ? '获取中…' : '获取可用模型'}
                </button>
              </div>
              <datalist id="model-name-options">
                {models.map((model) => <option key={model} value={model} />)}
              </datalist>
              <p className="ac-help">先「获取可用模型」，再从下拉中选择；也可以直接手动输入。</p>
            </div>
            {modelMessage && <p className={`tikhub-message ${modelMessage.tone}`} role="status">{modelMessage.text}</p>}
            <div className="ac-actions">
              <button type="button" className="ac-btn secondary" onClick={() => void saveAndTest()} disabled={testing || saving || !localConfig.modelName.trim()}>
                <PlugZap size={14} />{testing ? '保存并测试中…' : '保存并测试连接'}
              </button>
              <button type="submit" className="ac-btn primary" disabled={saving || testing}>{saving ? '保存中…' : '保存模型配置'}</button>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}

function SharePanel() {
  return (
    <div className="ac-stack">
      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><Smartphone size={15} /> iPhone 分享导入</h2>
          <p>安装「保存到 SynthAI」快捷指令后，在手机上的 X 或微信里看到好文章，直接从分享菜单保存进文章库，无需打开电脑。</p>
        </div>
        <div className="ac-set-main">
          <div className="share-flow" style={{ margin: 0, padding: 0, borderBottom: 0 }}>
            <span><Share2 size={16} /> X / 微信分享</span><ArrowRight size={15} />
            <span><Smartphone size={16} /> 保存到 SynthAI</span><ArrowRight size={15} />
            <span>文章库</span>
          </div>
          <p className="ac-help">完整设置（网站地址确认、iCloud 一键安装、手动创建指引）在独立页面完成。</p>
          <Link to="/admin/settings/share" className="ac-btn primary">打开分享设置 <ArrowRight size={14} /></Link>
        </div>
      </section>
    </div>
  );
}

export default function AdminSettings() {
  const fetchConfig = useAppStore((state) => state.fetchConfig);
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab') as TabId | null;
  const tab: TabId = TABS.some(t => t.id === tabParam) ? (tabParam as TabId) : 'tikhub';

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);

  return (
    <div className="ac-settings-page">
      <nav className="ac-tabs" aria-label="配置分区">
        {TABS.map(({ id, label }) => (
          <button
            type="button"
            key={id}
            className={id === tab ? 'active' : ''}
            aria-current={id === tab ? 'page' : undefined}
            onClick={() => setParams(id === 'tikhub' ? {} : { tab: id }, { replace: true })}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="ac-settings-content">
        {tab === 'tikhub' && <TikHubPanel />}
        {tab === 'model' && <ModelPanel />}
        {tab === 'share' && <SharePanel />}
      </div>
    </div>
  );
}
