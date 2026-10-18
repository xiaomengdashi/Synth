import { useEffect, useState } from 'react';
import { ChevronDown, Loader2, RefreshCw, ShieldCheck } from 'lucide-react';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { adminFetch } from '../../../utils/adminAuth';

interface CliConfig {
  installed: boolean;
  credentials_configured: boolean;
  auth_token_configured: boolean;
  ct0_configured: boolean;
  auth_token_masked: string;
  ct0_masked: string;
  source: 'config' | 'environment' | null;
  has_saved_credentials: boolean;
  executable: string;
  effective_executable: string;
}

interface Verification {
  verified: boolean;
  message: string;
  checked_at: string;
  account?: { name: string; screen_name: string };
}

async function requestConfig(init?: RequestInit): Promise<CliConfig> {
  const response = await adminFetch('/api/v1/config/twitter-cli', init);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'X 登录配置请求失败，请重试。');
  return data;
}

export default function TwitterCliSettingsPanel() {
  const [config, setConfig] = useState<CliConfig | null>(null);
  const [authToken, setAuthToken] = useState('');
  const [ct0, setCt0] = useState('');
  const [executable, setExecutable] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void requestConfig({ signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setConfig(data); setExecutable(data.executable);
    }).catch(error => {
      if (!controller.signal.aborted) setMessage({ tone: 'error', text: error instanceof Error ? error.message : '读取失败。' });
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  const refresh = async () => {
    setLoading(true); setMessage(null); setVerification(null);
    try {
      const data = await requestConfig();
      setConfig(data);
      if (!config) setExecutable(data.executable);
      window.dispatchEvent(new Event('twitter-cli-config-updated'));
      setMessage({ tone: 'success', text: '安装状态已更新。' });
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '检查失败。' });
    } finally { setLoading(false); }
  };

  const verify = async () => {
    setVerifying(true); setMessage(null); setVerification(null);
    try {
      const response = await adminFetch('/api/v1/config/twitter-cli/verify', { method: 'POST' });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data) throw new Error(typeof data?.detail === 'string' ? data.detail : '验证请求失败，请稍后重试。');
      setVerification(data);
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '验证请求失败。' });
    } finally { setVerifying(false); }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!config) return;
    setMessage(null);
    if (!config.has_saved_credentials && (!!authToken.trim() !== !!ct0.trim())) {
      setMessage({ tone: 'error', text: '请同时填写同一账号的 auth_token 和 ct0。' });
      return;
    }
    setSaving(true); setVerification(null);
    try {
      const data = await requestConfig({ method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ authToken, ct0, executable }) });
      setConfig(data); setExecutable(data.executable); setAuthToken(''); setCt0('');
      window.dispatchEvent(new Event('twitter-cli-config-updated'));
      setMessage({ tone: 'success', text: '配置已保存，可验证登录态。' });
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '保存失败。' });
    } finally { setSaving(false); }
  };

  const clear = async () => {
    setSaving(true); setMessage(null); setVerification(null);
    try {
      const data = await requestConfig({ method: 'DELETE' });
      setConfig(data); setAuthToken(''); setCt0(''); setConfirmClear(false);
      window.dispatchEvent(new Event('twitter-cli-config-updated'));
      setMessage({ tone: 'success', text: data.source === 'environment' ? '后台凭据已清除，现使用环境变量。' : '登录凭据已清除。' });
    } catch (error) {
      setConfirmClear(false);
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '清除失败。' });
    } finally { setSaving(false); }
  };

  const dirty = config !== null && (!!authToken.trim() || !!ct0.trim() || executable.trim() !== config.executable);
  const busy = loading || saving || verifying;

  const account = verification?.verified ? verification.account : undefined;
  const connectionTitle = account?.name ?? (config?.credentials_configured ? '登录凭据已配置' : '尚未配置登录凭据');
  const connectionState = loading ? '读取中' : verifying ? '验证中' : verification?.verified ? '已验证' : verification ? '验证未通过' : config && !config.installed ? 'CLI 未就绪' : config?.credentials_configured ? '待验证' : '未配置';

  return (
    <section className="ac-set-card twitter-cli-panel" aria-busy={busy}>
      <div className="ac-set-side">
        <h1>X 登录配置</h1>
        <p>用于获取 X 推文和长文。</p>
      </div>
      <div className="ac-set-main twitter-cli-settings">
        <div className={`twitter-cli-connection${verification?.verified ? ' is-verified' : ''}`} aria-label="X 连接状态">
          <div className="twitter-cli-connection-row">
            <span className="twitter-cli-connection-icon" aria-hidden="true"><ShieldCheck size={21} /></span>
            <div className="twitter-cli-connection-copy" role="status">
              <div className="twitter-cli-connection-heading"><strong>{loading ? '正在读取配置…' : connectionTitle}</strong><span className="twitter-cli-state">{connectionState}</span></div>
              <div className="twitter-cli-connection-meta">
                {account ? <a href={`https://x.com/${encodeURIComponent(account.screen_name)}`} target="_blank" rel="noreferrer">@{account.screen_name}</a>
                  : <span>{verifying ? '正在连接 X…' : dirty ? '先保存修改，再验证。' : config && !config.installed ? '在高级设置中检查 CLI 安装' : config?.credentials_configured ? '验证后显示当前账号' : '填写下方两项凭据开始连接'}</span>}
                {verification && <time dateTime={verification.checked_at} title={new Date(verification.checked_at).toLocaleString('zh-CN', { hour12: false })}>
                  {new Date(verification.checked_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })} 验证
                </time>}
              </div>
            </div>
            <button type="button" className="ac-btn secondary twitter-cli-verify" aria-label="验证 X 登录态" onClick={() => void verify()} disabled={busy || dirty || !config?.installed || !config?.credentials_configured}>
              {verifying && <Loader2 size={13} className="animate-spin" />}{verifying ? '验证中…' : verification?.verified ? '重新验证' : '验证登录态'}
            </button>
          </div>
          {verification && !verification.verified && <p className="twitter-cli-connection-error" role="alert">{verification.message}</p>}
        </div>
        <form onSubmit={save}>
          <div className="ac-grid-2">
            <div className="ac-field">
              <label htmlFor="twitter-auth-token"><span>auth_token</span>{config?.auth_token_configured && <code>{config.auth_token_masked}</code>}</label>
              <input id="twitter-auth-token" className="ac-input" type="password" autoComplete="new-password" spellCheck={false} maxLength={4096}
                disabled={busy || !config} value={authToken} onChange={event => { setAuthToken(event.target.value); setVerification(null); }}
                placeholder={config?.auth_token_configured ? '留空保留当前值' : '粘贴 auth_token'} />
            </div>
            <div className="ac-field">
              <label htmlFor="twitter-ct0"><span>ct0</span>{config?.ct0_configured && <code>{config.ct0_masked}</code>}</label>
              <input id="twitter-ct0" className="ac-input" type="password" autoComplete="new-password" spellCheck={false} maxLength={4096}
                disabled={busy || !config} value={ct0} onChange={event => { setCt0(event.target.value); setVerification(null); }}
                placeholder={config?.ct0_configured ? '留空保留当前值' : '粘贴 ct0'} />
            </div>
          </div>
          <details className="twitter-cli-cookie-help">
            <summary>如何获取 Cookie？<ChevronDown size={12} /></summary>
            <ol>
              <li>在浏览器登录 X，打开开发者工具。</li>
              <li>进入 Application → Cookies → x.com，复制 auth_token 和 ct0 的值。</li>
              <li>将同一账号的两个值填入上方并保存。凭据仅保存在服务器。</li>
            </ol>
          </details>
          <details className="twitter-cli-advanced">
            <summary><span>高级设置</span><span className="twitter-cli-advanced-preview">{config?.executable ? '自定义 CLI 路径' : '自动查找 CLI'}<ChevronDown size={14} /></span></summary>
            <div className="twitter-cli-advanced-content">
              <div className="twitter-cli-installation">
                <span>{!config ? '状态未读取' : config.installed ? 'twitter-cli 已安装' : '未找到 twitter-cli'}</span>
                <button type="button" className="ac-btn secondary" onClick={() => void refresh()} disabled={busy}><RefreshCw size={12} />{loading ? '检测中…' : '重新检测'}</button>
              </div>
              <div className="ac-field">
                <label htmlFor="twitter-executable">CLI 路径 <span className="settings-optional">可选</span></label>
                <input id="twitter-executable" className="ac-input" autoComplete="off" spellCheck={false} maxLength={2048}
                  disabled={busy || !config} value={executable} onChange={event => { setExecutable(event.target.value); setVerification(null); }} placeholder="自动查找，无需填写" />
                <p className="ac-help">留空使用环境变量或系统 PATH。当前：<code>{config?.effective_executable ?? '—'}</code></p>
              </div>
              <div className="twitter-cli-advanced-footer">
                <span>凭据来源：{config?.source === 'config' ? '后台保存' : config?.source === 'environment' ? '环境变量' : '未配置'}</span>
                {config?.has_saved_credentials && <button type="button" className="twitter-cli-clear" disabled={busy} onClick={() => setConfirmClear(true)}>清除登录凭据</button>}
              </div>
            </div>
          </details>
          {message && <p className={`tikhub-message ${message.tone}`} role={message.tone === 'error' ? 'alert' : 'status'}>{message.text}</p>}
          <div className="ac-actions">
            <button type="submit" className="ac-btn primary" disabled={busy || !dirty}>{saving ? '保存中…' : '保存配置'}</button>
          </div>
        </form>
      </div>
      <ConfirmDialog open={confirmClear} title="清除 X 登录凭据？" description="清除后台保存的 auth_token 和 ct0；如有环境变量配置，将恢复使用。" confirmText="清除凭据" busy={saving} onConfirm={() => void clear()} onCancel={() => setConfirmClear(false)} />
    </section>
  );
}
