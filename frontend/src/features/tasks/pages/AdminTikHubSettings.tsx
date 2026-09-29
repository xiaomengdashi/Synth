import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Bird, KeyRound, RefreshCw, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import { dateTime, money, requestJson } from '../../tikhub/client';
import type { Account, KeyStatus } from '../../tikhub/types';
import AdminPageHeader from '../components/AdminPageHeader';

export default function AdminTikHubSettings() {
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
      setNotice('Key 验证通过并已保存，后续查询将使用此 Key。');
      // Refresh public metadata only. Never post a placeholder back to config.
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
      setNotice(data.configured ? '已移除页面保存的 Key，当前使用服务器环境变量。' : '已移除保存的 Key。');
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
    <div className="tikhub-page">
      <AdminPageHeader eyebrow="Settings / TikHub" title="TikHub 数据服务"
        description="一次配置 Key，查看账户与用量，查询各平台的内容、用户、评论和搜索数据。"
        actions={<Link to="/admin/settings" className="secondary-button"><ArrowLeft size={14} /> 配置总览</Link>} />
      <nav className="tikhub-tabs" aria-label="TikHub 页面">
        <Link className="active" aria-current="page" to="/admin/settings/tikhub">Key 与账户</Link>
        <Link to="/admin/tikhub/query">多平台查询 <ArrowRight size={14} /></Link>
      </nav>
      <div className="settings-layout">
        <section className="settings-panel settings-form-panel">
          <h2><KeyRound size={16} /> API Key 设置</h2>
          <p>在 <a href="https://user.tikhub.io" target="_blank" rel="noreferrer">TikHub 控制台</a> 创建 Key。验证通过后保存，现有 Key 会在验证失败时保留。</p>
          <div className="tikhub-key-status">
            <span className={key?.configured ? 'config-status ready' : 'config-status'}>
              {key === null ? '读取配置中' : key.configured ? '已配置' : '尚未配置'}
            </span>
            {key?.configured && <><code>{key.masked_key}</code><span>{key.source === 'environment' ? '来自服务器环境变量' : '来自本页设置'}</span></>}
          </div>
          <form onSubmit={save}>
            <div className="form-field">
              <label htmlFor="tikhub-key">TikHub API Key</label>
              <input id="tikhub-key" type="password" autoComplete="new-password" spellCheck={false} value={apiKey}
                onChange={event => setApiKey(event.target.value)} maxLength={4096} disabled={saving}
                placeholder={key?.configured ? '输入新 Key 以更换' : '粘贴 TikHub API Key'} />
              <p className="form-help">Key 仅保存在后端，不会回传到浏览器。保存的 Key 优先于环境变量。</p>
            </div>
            {error && <p className="tikhub-message error" role="alert">{error}</p>}
            {notice && <p className="tikhub-message success" role="status">{notice}</p>}
            <div className="modal-footer">
              {key?.has_saved_key && <button type="button" className="secondary-button" onClick={() => void remove()} disabled={saving}>移除已保存 Key</button>}
              <button type="submit" className="primary-button" disabled={saving || !apiKey.trim()}>{saving ? '正在处理…' : '验证并保存'}</button>
            </div>
          </form>
        </section>
        <section className="settings-panel settings-form-panel">
          <h2><Bird size={16} /> 数据查询</h2>
          <p>按平台浏览查询目录，选择内容详情、用户信息、评论列表或搜索接口。参数和必填项由官方接口定义提供。</p>
          <div className="tikhub-platform-preview"><span>抖音</span><span>X / Twitter</span><span>Bilibili</span><span>微信</span><span>小红书</span><span>更多平台</span></div>
          <p className="form-help">也可在“账户与计费”分类中查询接口价格、价格估算和阶梯折扣。查询可能消耗 TikHub 额度，以实际接口计费为准。</p>
          <Link to="/admin/tikhub/query" className="primary-button tikhub-query-link">进入多平台查询 <ArrowRight size={14} /></Link>
        </section>
      </div>
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
    </div>
  );
}
