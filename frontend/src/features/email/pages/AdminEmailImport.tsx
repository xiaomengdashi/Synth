import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Mail, PlugZap, Save } from 'lucide-react';
import { adminFetch } from '../../../utils/adminAuth';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../../tasks/components/AdminPageHeader';

type FetchResult = {
  fetched: number;
  imported: { id: string; title: string; filename: string }[];
  skipped: { subject: string; reason: string }[];
};

type Message = { tone: 'success' | 'error'; text: string } | null;

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const response = await adminFetch(url, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { detail?: string } | null)?.detail;
    throw new Error(typeof detail === 'string' ? detail : `请求失败（HTTP ${response.status}）`);
  }
  return data as T;
}

const DAY_OPTIONS = [7, 30, 90, 180, 365];

function EmailPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [message, setMessage] = useState<Message>(null);
  const [result, setResult] = useState<FetchResult | null>(null);
  const [days, setDays] = useState(30);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const save = async (): Promise<boolean> => {
    setSaving(true);
    const ok = await setConfig(localConfig);
    setSaving(false);
    if (!ok) setMessage({ tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    return ok;
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(null);
    if (await save()) setMessage({ tone: 'success', text: '邮箱配置已保存。' });
  };

  const handleTest = async () => {
    setTesting(true); setMessage(null);
    if (!(await save())) { setTesting(false); return; }
    try {
      const data = await postJson<{ ok: boolean; recent_count: number }>('/api/v1/email/test', { days });
      setMessage({ tone: 'success', text: `连接成功，白名单发件人近 30 天有 ${data.recent_count} 封带 md 附件的邮件。` });
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : '连接测试失败。' });
    } finally { setTesting(false); }
  };

  const handleFetch = async () => {
    setFetching(true); setMessage(null); setResult(null);
    if (!(await save())) { setFetching(false); return; }
    try {
      const data = await postJson<FetchResult>('/api/v1/email/fetch', { days });
      setResult(data);
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : '拉取失败。' });
    } finally { setFetching(false); }
  };

  return (
    <div className="ac-stack">
      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><Mail size={15} /> 邮箱配置
            <span className={config.imapConfigured ? 'ac-badge success' : 'ac-badge pending'}>
              {config.imapConfigured ? '已配置' : '尚未配置'}
            </span>
          </h2>
          <p>在 163 网页版「设置 → POP3/SMTP/IMAP」开启 IMAP 服务并生成客户端授权码；授权码不是邮箱登录密码。</p>
        </div>
        <div className="ac-set-main">
          <form onSubmit={handleSave}>
            <div className="ac-field">
              <label htmlFor="imap-host">IMAP 服务器</label>
              <input id="imap-host" className="ac-input" value={localConfig.imapHost ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapHost: event.target.value })} placeholder="imap.163.com" />
            </div>
            <div className="ac-field">
              <label htmlFor="imap-user">邮箱账号</label>
              <input id="imap-user" className="ac-input" type="email" value={localConfig.imapUser ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapUser: event.target.value })} placeholder="you@163.com" />
            </div>
            <div className="ac-field">
              <label htmlFor="imap-password">客户端授权码</label>
              <input id="imap-password" className="ac-input" type="password" autoComplete="new-password" value={localConfig.imapPassword ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapPassword: event.target.value })} placeholder={config.imapConfigured ? '已配置，输入新授权码可更换' : '客户端授权码'} />
              <p className="ac-help">仅保存在后端数据库，页面只显示掩码。</p>
            </div>
            <div className="ac-field">
              <label htmlFor="imap-whitelist">发件人白名单</label>
              <input id="imap-whitelist" className="ac-input" value={localConfig.imapSenderWhitelist ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapSenderWhitelist: event.target.value })} placeholder="friend@qq.com, other@163.com" />
              <p className="ac-help">只拉取这些发件人的邮件，多个地址用逗号分隔。</p>
            </div>
            <div className="ac-field">
              <label htmlFor="imap-days">拉取范围</label>
              <select id="imap-days" className="ac-input" style={{ width: 'auto' }} value={days} onChange={(event) => setDays(Number(event.target.value))}>
                {DAY_OPTIONS.map((option) => (
                  <option key={option} value={option}>近 {option} 天</option>
                ))}
              </select>
              <p className="ac-help">「测试连接」和「拉取邮件」按此范围拉取，已入库的不会重复。</p>
            </div>
            {message && <p className={`tikhub-message ${message.tone}`} role="status">{message.text}</p>}
            <div className="ac-actions">
              <button type="button" className="ac-btn secondary" onClick={() => void handleTest()} disabled={testing || fetching}>
                <PlugZap size={14} />{testing ? '测试中…' : '测试连接'}
              </button>
              <button type="button" className="ac-btn primary" onClick={() => void handleFetch()} disabled={fetching || testing}>
                <Download size={14} />{fetching ? '拉取中…' : '拉取邮件'}
              </button>
              <button type="submit" className="ac-btn secondary" disabled={saving || testing || fetching}>
                <Save size={14} />{saving ? '保存中…' : '保存配置'}
              </button>
            </div>
          </form>
        </div>
      </section>

      {result && (
        <section className="ac-set-card">
          <div className="ac-set-side">
            <h2><Download size={15} /> 本次拉取结果</h2>
            <p>白名单内符合条件的邮件 {result.fetched} 封，入库 {result.imported.length} 篇。</p>
          </div>
          <div className="ac-set-main">
            {result.imported.length > 0 && (
              <ul className="ac-help">
                {result.imported.map((item) => (
                  <li key={item.id}><Link to={`/article/${item.id}`}>{item.title}</Link>（{item.filename}）</li>
                ))}
              </ul>
            )}
            {result.imported.length === 0 && <p className="ac-help">本次没有新文章入库。</p>}
            {result.skipped.length > 0 && (
              <ul className="ac-help">
                {result.skipped.map((item, index) => (
                  <li key={`${item.subject}-${index}`}>{item.subject || '（无主题）'}：{item.reason}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

/** 邮箱导入：163 IMAP 配置、测试连接与手动拉取 */
export default function AdminEmailImport() {
  return (
    <div>
      <AdminPageHeader summary={<span>邮箱导入：拉取白名单发件人的 md 附件笔记</span>} />
      <div className="ac-settings-page"><div className="ac-settings-content">
        <EmailPanel />
      </div></div>
    </div>
  );
}
