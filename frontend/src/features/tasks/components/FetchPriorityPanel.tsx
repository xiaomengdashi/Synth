import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDown, ArrowRight, ArrowUp, Check, ChevronDown, CircleHelp, ExternalLink, Package, RotateCcw, Save } from 'lucide-react';
import { adminFetch } from '../../../utils/adminAuth';

type Priorities = Record<string, string[]>;
interface DeploymentRequirement {
  name: string;
  summary: string;
  condition: string;
  description: string;
  commands: { label: string; command: string }[];
  docs_url?: string;
  config_link?: { label: string; href: string };
}
interface FetchSettings {
  platforms: Record<string, { label: string; providers: string[]; requirements?: DeploymentRequirement[] }>;
  providers: Record<string, { label: string; description: string; status?: string }>;
  priorities: Priorities;
}

function DeploymentRequirements({ platform, requirements }: { platform: string; requirements: DeploymentRequirement[] }) {
  if (!requirements.length) return <p className="priority-no-dependencies">无需额外系统依赖</p>;
  return (
    <details className="priority-dependencies">
      <summary aria-label={`${platform} 部署依赖`}>
        <Package size={12} aria-hidden="true" />
        <span>{requirements.map(requirement => requirement.summary).join('；')}</span>
        <ChevronDown size={12} aria-hidden="true" />
      </summary>
      <div className="priority-dependency-content">
        <p className="priority-dependency-location">在运行后端的服务器执行；容器部署请安装在后端镜像中。</p>
        {requirements.map(requirement => (
          <section className="priority-dependency" key={requirement.name}>
            <h3>{requirement.name}</h3>
            <p className="priority-dependency-condition">{requirement.condition}</p>
            <p>{requirement.description}</p>
            {requirement.commands.map(command => (
              <div className="priority-install-command" key={command.label}>
                <span>{command.label}</span>
                <pre><code>{command.command}</code></pre>
              </div>
            ))}
            <div className="priority-dependency-links">
              {requirement.docs_url && <a href={requirement.docs_url} target="_blank" rel="noopener noreferrer">安装文档<ExternalLink size={11} /></a>}
              {requirement.config_link && <Link to={requirement.config_link.href}>{requirement.config_link.label}<ArrowRight size={11} /></Link>}
            </div>
          </section>
        ))}
      </div>
    </details>
  );
}

async function fetchSettings(init?: RequestInit): Promise<FetchSettings> {
  const response = await adminFetch('/api/v1/config/fetch-priorities', init);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '获取方式设置请求失败，请重试。');
  return data;
}

export default function FetchPriorityPanel() {
  const [settings, setSettings] = useState<FetchSettings | null>(null);
  const [priorities, setPriorities] = useState<Priorities>({});
  const [loading, setLoading] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setMessage(null);
    try {
      const data = await fetchSettings({ signal });
      if (signal?.aborted) return;
      setSettings(data); setPriorities(data.priorities);
    } catch (error) {
      if (!signal?.aborted) setMessage({ tone: 'error', text: error instanceof Error ? error.message : '读取失败。' });
    } finally { if (!signal?.aborted) setLoading(false); }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    const refreshStatus = () => {
      void fetchSettings({ signal: controller.signal }).then(data => {
        // Refresh availability without discarding an unsaved priority order.
        setSettings(current => current ? { ...current, providers: data.providers } : current);
      }).catch(() => { /* The configuration page reports its own request errors. */ });
    };
    window.addEventListener('twitter-cli-config-updated', refreshStatus);
    return () => { controller.abort(); window.removeEventListener('twitter-cli-config-updated', refreshStatus); };
  }, []);

  const move = (platform: string, index: number, direction: number) => {
    setMessage(null);
    setPriorities(current => {
      const order = [...current[platform]];
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= order.length) return current;
      [order[index], order[nextIndex]] = [order[nextIndex], order[index]];
      return { ...current, [platform]: order };
    });
  };

  const save = async () => {
    setSaving(true); setMessage(null);
    try {
      const data = await fetchSettings({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ priorities }) });
      setSettings(data); setPriorities(data.priorities);
      setMessage({ tone: 'success', text: '获取优先级已保存，下次导入或重新获取时生效。' });
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '保存失败，请重试。' });
    } finally { setSaving(false); }
  };

  const dirty = settings !== null && JSON.stringify(priorities) !== JSON.stringify(settings.priorities);

  return (
    <section className="fetch-priority-workspace" aria-busy={loading || saving}>
      <header className="priority-page-heading">
        <div><h1>获取优先级</h1><p>按顺序获取内容，失败或无有效正文时自动切换。</p></div>
        <button type="button" className="priority-help-toggle" aria-expanded={helpOpen} aria-controls="priority-help" onClick={() => setHelpOpen(open => !open)}><CircleHelp size={15} />使用说明<ChevronDown size={13} /></button>
      </header>
      <div id="priority-help" className="priority-help" hidden={!helpOpen}>
        <p>使用箭头调整尝试顺序，保存后对新导入与重新获取生效。正在处理的任务不受影响。</p>
        {settings && <dl>{Object.entries(settings.providers).map(([provider, method]) => <div key={provider}><dt>{method.label}</dt><dd>{method.description}</dd></div>)}</dl>}
      </div>
      {loading ? <div className="priority-loading" role="status">正在读取获取方式…</div> : settings ? <>
        <div className="priority-table">
          <div className="priority-table-heading" aria-hidden="true"><span>内容来源</span><span>获取顺序<small>箭头调整优先级</small></span></div>
          <div className="priority-rows">
            {Object.entries(settings.platforms).map(([platform, info]) => {
              const order = priorities[platform] ?? [];
              const adjustable = order.length > 1;
              const graphql = order.includes('x_graphql');
              const cliStatus = graphql ? settings.providers.x_graphql?.status : order.includes('twitter_cli') ? settings.providers.twitter_cli?.status : undefined;
              return <section className="priority-row" key={platform} aria-label={info.label}>
                <h2>{info.label}</h2>
                <div className="priority-row-content">
                  <ol className={`priority-chain${adjustable ? '' : ' is-fixed'}`} aria-label={`${info.label} 获取顺序`}>
                    {order.map((provider, index) => {
                      const method = settings.providers[provider];
                      return <li className="priority-chain-item" key={provider}>
                        {index > 0 && <ArrowRight size={14} className="priority-chain-connector" aria-hidden="true" />}
                        <div className={`priority-method${index === 0 && adjustable ? ' is-first' : ''}`}>
                          {adjustable && <span className="priority-rank" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>}
                          <strong>{method.label}</strong>
                          <span className="priority-method-state">{adjustable && index === 0 ? '优先' : ''}</span>
                          {adjustable && <div className="priority-method-actions">
                            <button type="button" onClick={() => move(platform, index, -1)} disabled={saving || index === 0} aria-label={`上移 ${method.label}（${info.label}）`} title="提高优先级"><ArrowUp size={13} /></button>
                            <button type="button" onClick={() => move(platform, index, 1)} disabled={saving || index === order.length - 1} aria-label={`下移 ${method.label}（${info.label}）`} title="降低优先级"><ArrowDown size={13} /></button>
                          </div>}
                        </div>
                      </li>;
                    })}
                  </ol>
                  {cliStatus && <p className="priority-cli-status" title={cliStatus}><span className={cliStatus.startsWith('已配置') ? 'is-ready' : ''} aria-hidden="true" />{graphql ? 'X 登录态' : 'twitter-cli'} {cliStatus.startsWith('已配置') ? '已配置' : graphql ? '未配置' : cliStatus}<span aria-hidden="true">·</span><Link to="/admin/tikhub?section=twitter-cli">登录配置</Link></p>}
                  <DeploymentRequirements platform={info.label} requirements={info.requirements ?? []} />
                </div>
              </section>;
            })}
          </div>
          <footer className="priority-savebar">
            <div className={`priority-save-status${dirty ? ' is-dirty' : ''}`} role="status">{dirty ? <span className="priority-unsaved-mark" aria-hidden="true" /> : <Check size={14} />}<strong>{dirty ? '有未保存的调整' : '当前配置已保存'}</strong><span>仅对新任务生效</span></div>
            <div className="priority-save-actions">
              <button type="button" className="priority-button secondary" disabled={saving} onClick={() => {
                setPriorities(Object.fromEntries(Object.entries(settings.platforms).map(([key, info]) => [key, [...info.providers]])));
                setMessage(null);
              }}><RotateCcw size={14} />恢复默认</button>
              <button type="button" className="priority-button primary" disabled={saving || !dirty} onClick={() => void save()}><Save size={14} />{saving ? '保存中…' : '保存更改'}</button>
            </div>
          </footer>
        </div>
      </> : <button type="button" className="priority-button secondary" onClick={() => void load()}>重新读取</button>}
      {message && <p className={`tikhub-message priority-message ${message.tone}`} role={message.tone === 'error' ? 'alert' : 'status'}>{message.text}</p>}
    </section>
  );
}
