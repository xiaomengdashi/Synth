import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Bird, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';

interface TikHubAccount {
  configured: boolean;
  api_key?: {
    name: string;
    created_at: string | null;
    expires_at: string | null;
    status: number;
    scopes_count: number;
  };
  user?: {
    email: string;
    balance: number;
    free_credit: number;
    is_active: boolean;
  };
  daily_usage?: {
    date: string;
    usage: number;
    total_request_per_day: number;
    paid_request_per_day: number;
    uri_counts: Record<string, number>;
  };
}

const ENDPOINT_LABELS: Record<string, string> = {
  '/api/v1/twitter/web/fetch_tweet_detail': 'X 推文/长文',
  '/api/v1/wechat_mp/v2/fetch_article_detail_h5': '公众号文章',
  '/api/v1/bilibili/web/fetch_video_parts': 'B站分P信息',
  '/api/v1/bilibili/web/bv_to_aid': 'B站 BV→AV 转换',
  '/api/v1/bilibili/web/fetch_one_video_v2': 'B站字幕',
  '/api/v1/tikhub/user/get_user_info': '账户信息查询',
  '/api/v1/tikhub/user/get_user_daily_usage': '每日用量查询',
};

const endpointLabel = (path: string) => ENDPOINT_LABELS[path] || path.split('/').slice(3).join('/');

export default function AdminTikHubSettings() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [apiKey, setApiKey] = useState('');
  const [account, setAccount] = useState<TikHubAccount | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loadAccount = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/v1/tikhub/account');
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '查询失败');
      setAccount(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { void loadAccount(); }, [loadAccount]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!apiKey.trim()) { setError('请填写 API Token。'); return; }
    setSaving(true); setError(''); setNotice('');
    try {
      const res = await fetch('/api/v1/tikhub/key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKey: apiKey.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '保存失败');
      setNotice(`Token 验证通过并已保存（${data.account.user.balance} 余额）。`);
      setApiKey('');
      await setConfig({ ...config, tikhubApiKey: 'configured' });
      await loadAccount();
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const usage = account?.daily_usage;
  const uriEntries = Object.entries(usage?.uri_counts || {}).sort((a, b) => b[1] - a[1]);

  return (
    <div>
      <AdminPageHeader eyebrow="Settings / 04 / TikHub" title="TikHub 抓取" description="X 推文/长文、公众号文章、Bilibili 视频统一通过 TikHub 第三方接口获取。" actions={<Link to="/admin/settings" className="secondary-button"><ArrowLeft size={14} /> 配置总览</Link>} />
      <div className="settings-layout">
        <section className="settings-panel">
          <h2><Bird size={16} /> API Token</h2>
          <p>在 <a href="https://user.tikhub.io" target="_blank" rel="noreferrer">user.tikhub.io</a> 控制台创建 Token 后填入。保存时会先验证 Token 有效性，验证通过才落盘。</p>
          <form onSubmit={save}>
            <div className="form-grid">
              <div className="form-field full">
                <label htmlFor="tikhub-key">TikHub API Token</label>
                <input id="tikhub-key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={config.tikhubApiKey ? '已配置，输入新 Token 可更换' : '在 TikHub 用户控制台创建'} />
              </div>
            </div>
            {error && <p className="form-help" style={{ color: '#f87171' }}>{error}</p>}
            {notice && <p className="form-help" style={{ color: '#4ade80' }}>{notice}</p>}
            <div className="modal-footer">
              <button type="submit" className="primary-button" disabled={saving}>{saving ? '验证中...' : '保存并验证'}</button>
            </div>
          </form>
        </section>

        <section className="settings-panel settings-form-panel">
          <h2><RefreshCw size={16} /> 账户信息 <button type="button" className="secondary-button" style={{ marginLeft: 8 }} onClick={() => void loadAccount()} disabled={loading}>{loading ? '刷新中...' : '刷新'}</button></h2>
          {!account?.configured ? (
            <p className="form-help">尚未配置 Token。</p>
          ) : account.user ? (
            <>
              <div className="form-grid">
                <div className="form-field"><label>余额</label><p style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>${account.user.balance.toFixed(3)}</p></div>
                <div className="form-field"><label>免费额度</label><p style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>${account.user.free_credit.toFixed(3)}</p></div>
                <div className="form-field"><label>Key 名称</label><p style={{ margin: 0 }}>{account.api_key?.name || '-'}（{account.api_key?.scopes_count ?? 0} 个端点权限）</p></div>
                <div className="form-field"><label>账户状态</label><p style={{ margin: 0 }}>{account.user.is_active ? '正常' : '异常'}</p></div>
              </div>
              {usage && (
                <>
                  <h2 style={{ marginTop: 20 }}>今日用量（{usage.date}）</h2>
                  <p style={{ margin: '0 0 8px' }}>花费 <strong>${usage.usage.toFixed(4)}</strong> · 共 <strong>{usage.total_request_per_day}</strong> 次请求（付费 {usage.paid_request_per_day} 次）</p>
                  {uriEntries.length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.9 }}>
                      {uriEntries.map(([path, count]) => (
                        <li key={path}>{endpointLabel(path)} × {count}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </>
          ) : (
            <p className="form-help" style={{ color: '#f87171' }}>{error || '账户信息加载失败，请刷新重试。'}</p>
          )}
        </section>
      </div>
    </div>
  );
}
