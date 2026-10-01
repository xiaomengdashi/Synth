import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { requestJson } from '../../tikhub/client';
import AdminPageHeader from '../components/AdminPageHeader';

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
    <section className="ac-card">
      <div className="ac-card-head">
        <h2 className="ac-card-title"><KeyRound size={15} />后台访问令牌</h2>
      </div>
      <div className="ac-card-body">
        <p className="ac-card-desc">重置进入后台所需的访问令牌。成功后本机自动使用新令牌；其他设备需要用新令牌重新登录。</p>
        <div className="ac-stack">
          <div className="ac-field">
            <label htmlFor="token-current">当前令牌</label>
            <input id="token-current" className="ac-input" type="password" value={current} onChange={(event) => { setCurrent(event.target.value); setError(''); }} autoComplete="current-password" />
          </div>
          <div className="ac-field">
            <label htmlFor="token-next">新令牌</label>
            <input id="token-next" className="ac-input" type="password" value={next} onChange={(event) => { setNext(event.target.value); setError(''); }} placeholder="至少 6 位" autoComplete="new-password" />
          </div>
          <div className="ac-field">
            <label htmlFor="token-confirm">确认新令牌</label>
            <input id="token-confirm" className="ac-input" type="password" value={confirmNext} onChange={(event) => { setConfirmNext(event.target.value); setError(''); }} autoComplete="new-password" />
          </div>
          {error ? <p className="ac-message error" role="alert">{error}</p> : null}
          <div className="ac-actions">
            <button type="button" className="ac-btn primary" onClick={() => void submit()} disabled={saving || !current.trim() || !next.trim() || !confirmNext.trim()}>
              {saving ? '重置中…' : '重置令牌'}
            </button>
          </div>
        </div>
        <p className="ac-help">忘记令牌时无法从后台恢复，需在服务器上清除 app_settings 表中 key 为 admin_token_hash 的记录后重新设置。</p>
      </div>
    </section>
  );
}

/** 重置进入后台所需的访问令牌 */
export default function AdminTokenSettings() {
  return (
    <div>
      <AdminPageHeader summary={<span>重置进入后台所需的访问令牌</span>} />
      <div className="ac-settings-page"><div className="ac-settings-content">
        <TokenPanel />
      </div></div>
    </div>
  );
}
