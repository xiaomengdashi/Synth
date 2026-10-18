import { useState } from 'react';
import { KeyRound, ShieldCheck } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { adminFetch, saveAdminToken } from '../../../utils/adminAuth';
import SettingsWorkspace from '../components/SettingsWorkspace';

function TokenPanel() {
  const pushToast = useAppStore((state) => state.pushToast);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmNext, setConfirmNext] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (next.trim().length < 6) {
      setError('新令牌至少 6 个字符');
      return;
    }
    if (next !== confirmNext) {
      setError('两次输入的新令牌不一致');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await adminFetch('/api/v1/admin-auth/token', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current: current.trim(), next: next.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || '重置失败');
      }
      saveAdminToken(next.trim());
      setCurrent(''); setNext(''); setConfirmNext('');
      pushToast({ title: '访问令牌已重置，本机已自动续用新令牌', tone: 'success' });
    } catch (err) {
      setError(err instanceof Error ? err.message : '重置失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="ac-set-card">
      <div className="ac-set-side">
        <h1><KeyRound size={15} /> 后台访问令牌</h1>
        <p>更新进入后台所需的访问令牌，保护控制台与配置数据。</p>
      </div>
      <div className="ac-set-main">
        <div className="settings-inline-note"><ShieldCheck size={18} aria-hidden="true" /><p><strong>重置后，本机将自动续用新令牌</strong><span>其他设备需要使用新令牌重新登录。</span></p></div>
        <form onSubmit={event => { event.preventDefault(); void submit(); }}>
          <div className="ac-field">
            <label htmlFor="token-current">当前令牌</label>
            <input id="token-current" className="ac-input" type="password" required value={current} onChange={(event) => { setCurrent(event.target.value); setError(''); }} placeholder="输入当前正在使用的令牌" autoComplete="current-password" />
          </div>
          <div className="ac-field">
            <label htmlFor="token-next">新令牌</label>
            <input id="token-next" className="ac-input" type="password" required value={next} onChange={(event) => { setNext(event.target.value); setError(''); }} placeholder="设置至少 6 个字符的新令牌" autoComplete="new-password" />
            <p className="ac-help">建议使用字母、数字与符号的组合。</p>
          </div>
          <div className="ac-field">
            <label htmlFor="token-confirm">确认新令牌</label>
            <input id="token-confirm" className="ac-input" type="password" required value={confirmNext} onChange={(event) => { setConfirmNext(event.target.value); setError(''); }} placeholder="再次输入新令牌" autoComplete="new-password" />
          </div>
          {error ? <p className="ac-message error" role="alert">{error}</p> : null}
          <div className="ac-actions">
            <button type="submit" className="ac-btn primary" disabled={saving || !current.trim() || !next.trim() || !confirmNext.trim()}>
              <KeyRound size={14} />
              {saving ? '重置中…' : '重置令牌'}
            </button>
          </div>
        </form>
        <details className="settings-help-disclosure"><summary>忘记访问令牌怎么办？</summary><p>需在服务器上清除 app_settings 表中 key 为 admin_token_hash 的记录后重新设置。</p></details>
      </div>
    </section>
  );
}

/** 重置进入后台所需的访问令牌 */
export default function AdminTokenSettings() {
  return (
    <SettingsWorkspace sections={[
      { id: 'token', label: '访问令牌', content: <TokenPanel /> },
    ]} />
  );
}
