import { useEffect, useState } from 'react';
import { getAdminToken } from '../utils/adminAuth';

export type AdminVerifyStatus = 'checking' | 'anonymous' | 'verified';

/**
 * 前台读者页的管理员身份探测：localStorage 令牌经 /admin-auth/login 复验通过才算已登录。
 * 导入/删除/重新获取等管理动作在前台只对站长露出，访客不可见；
 * focus 与 storage 事件触发重验，与 AdminGate、删除按钮同一口径。
 *
 * checking 是"尚无结论"（正在复验或本地存有令牌待确认），anonymous 是确认未登录。
 * 提交类调用方在 checking 态可照常发起请求，由后端令牌裁决兜底。
 */
export default function useVerifiedAdminToken(): { status: AdminVerifyStatus; token: string } {
  const [state, setState] = useState<{ status: AdminVerifyStatus; token: string }>({ status: 'checking', token: '' });

  useEffect(() => {
    let controller: AbortController | undefined;
    const verify = async () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      const token = getAdminToken();
      if (!token) {
        setState({ status: 'anonymous', token: '' });
        return;
      }
      try {
        const response = await fetch('/api/v1/admin-auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
          signal: current.signal,
        });
        if (current.signal.aborted) return;
        if (response.ok && getAdminToken() === token) setState({ status: 'verified', token });
        else setState({ status: 'anonymous', token: '' });
      } catch {
        if (!current.signal.aborted) setState({ status: 'anonymous', token: '' });
      }
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'synthai_admin_token' || event.key === null) void verify();
    };
    void verify();
    window.addEventListener('focus', verify);
    window.addEventListener('storage', onStorage);
    return () => {
      controller?.abort();
      window.removeEventListener('focus', verify);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  return state;
}
