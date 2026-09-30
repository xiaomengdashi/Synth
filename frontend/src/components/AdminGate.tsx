import { useEffect, useState } from 'react';
import { KeyRound, Loader2, ShieldCheck } from 'lucide-react';
import { BrandMark } from './Layout';
import { clearAdminToken, getAdminToken, saveAdminToken } from '../utils/adminAuth';

type GateState = 'checking' | 'setup' | 'login' | 'passed';

/**
 * 后台访问门:未初始化时引导设置令牌,已初始化时校验令牌。
 * 校验通过后令牌存于 localStorage,刷新浏览器免重新输入;
 * 服务端只保存令牌哈希,修改令牌或清缓存后需重新验证。
 */
export default function AdminGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>('checking');
  const [token, setToken] = useState('');
  const [confirmToken, setConfirmToken] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const statusRes = await fetch('/api/v1/admin-auth/status');
        const status = await statusRes.json();
        if (cancelled) return;
        if (!status.initialized) {
          setState('setup');
          return;
        }
        const saved = getAdminToken();
        if (!saved) {
          setState('login');
          return;
        }
        const loginRes = await fetch('/api/v1/admin-auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: saved }),
        });
        if (cancelled) return;
        if (loginRes.ok) {
          setState('passed');
        } else {
          clearAdminToken();
          setState('login');
        }
      } catch {
        if (!cancelled) setState('login');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const submitSetup = async () => {
    if (token.trim().length < 6) {
      setError('令牌至少 6 个字符');
      return;
    }
    if (token !== confirmToken) {
      setError('两次输入不一致');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await fetch('/api/v1/admin-auth/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token.trim() }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || '设置失败');
      saveAdminToken(token.trim());
      setState('passed');
    } catch (err) {
      setError(err instanceof Error ? err.message : '设置失败，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const submitLogin = async () => {
    if (!token.trim()) {
      setError('请输入访问令牌');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await fetch('/api/v1/admin-auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token.trim() }),
      });
      if (!res.ok) throw new Error('访问令牌不正确');
      saveAdminToken(token.trim());
      setState('passed');
    } catch (err) {
      setError(err instanceof Error ? err.message : '校验失败，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  if (state === 'passed') return <>{children}</>;

  if (state === 'checking') {
    return (
      <div className="admin-gate">
        <div className="admin-gate-card"><Loader2 size={20} className="animate-spin" /></div>
      </div>
    );
  }

  const isSetup = state === 'setup';
  return (
    <div className="admin-gate">
      <form
        className="admin-gate-card"
        onSubmit={(event) => {
          event.preventDefault();
          void (isSetup ? submitSetup() : submitLogin());
        }}
      >
        <div className="admin-gate-brand">
          <BrandMark size={30} />
          <span>SynthAI 控制台</span>
        </div>
        <h1>{isSetup ? '设置后台访问令牌' : '输入后台访问令牌'}</h1>
        <p>{isSetup
          ? '首次使用请设置一个访问令牌，此后进入后台需要验证。令牌以加密形式保存在服务端。'
          : '令牌已在本机保存，刷新无需重新输入；清空浏览器缓存后需再次验证。'}</p>
        <label className="admin-gate-field">
          {isSetup ? <KeyRound size={15} /> : <ShieldCheck size={15} />}
          <input
            type="password"
            value={token}
            onChange={(event) => { setToken(event.target.value); setError(''); }}
            placeholder={isSetup ? '设置令牌（至少 6 位）' : '访问令牌'}
            autoFocus
            aria-label="后台访问令牌"
          />
        </label>
        {isSetup ? (
          <label className="admin-gate-field">
            <KeyRound size={15} />
            <input
              type="password"
              value={confirmToken}
              onChange={(event) => { setConfirmToken(event.target.value); setError(''); }}
              placeholder="再输入一次确认"
              aria-label="确认后台访问令牌"
            />
          </label>
        ) : null}
        {error ? <p className="admin-gate-error" role="alert">{error}</p> : null}
        <button type="submit" className="admin-gate-submit" disabled={busy}>
          {busy ? <><Loader2 size={14} className="animate-spin" />验证中</> : isSetup ? '保存并进入后台' : '进入后台'}
        </button>
      </form>
    </div>
  );
}
