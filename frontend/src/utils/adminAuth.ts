/** 后台访问令牌:浏览器端持久化(清缓存即失效),管理写请求统一携带。 */

const TOKEN_KEY = 'synthai_admin_token';

export function getAdminToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function saveAdminToken(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // 隐私模式等存储失败时仅本次会话可用
  }
}

export function clearAdminToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

/** 管理类写接口请求:自动附带 X-Admin-Token。 */
export function adminFetch(input: RequestInfo, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getAdminToken();
  if (token) headers.set('X-Admin-Token', token);
  return fetch(input, { ...init, headers });
}
