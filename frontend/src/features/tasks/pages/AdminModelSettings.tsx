import { useEffect, useState } from 'react';
import { AudioLines, Cpu, ListChecks, PlugZap, SlidersHorizontal } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { requestJson } from '../../tikhub/client';
import AdminPageHeader from '../components/AdminPageHeader';

type Message = { tone: 'success' | 'error'; text: string } | null;

/** 表单里的 Key 是掩码时不下发，后端改用已保存的真实 Key */
function effectiveKey(value: string | undefined): string | undefined {
  return (value ?? '').includes('•') ? undefined : ((value ?? '').trim() || undefined);
}

function ConnectionPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [models, setModels] = useState<string[]>([]);
  const [listing, setListing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const configured = Boolean(config.apiKeyConfigured && config.baseUrl && config.modelName);
  const apiKey = effectiveKey(localConfig.apiKey);
  const persistConfig = () => setConfig(localConfig);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true); setMessage(null);
    const ok = await persistConfig();
    setMessage(ok
      ? { tone: 'success', text: '模型连接配置已保存。' }
      : { tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    setSaving(false);
  };

  const saveAndTest = async () => {
    setTesting(true); setMessage(null);
    const saved = await persistConfig();
    if (!saved) {
      setMessage({ tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
      setTesting(false);
      return;
    }
    try {
      const data = await requestJson<{ ok: boolean; latency_ms: number }>('/api/v1/models/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: localConfig.baseUrl, apiKey, model: localConfig.modelName }),
      });
      setMessage({ tone: 'success', text: `配置已保存，模型「${localConfig.modelName}」连接成功，响应 ${data.latency_ms} ms。` });
    } catch (e) {
      setMessage({ tone: 'error', text: `配置已保存，但连接测试失败：${e instanceof Error ? e.message : '未知错误'}` });
    } finally { setTesting(false); }
  };

  const fetchModels = async () => {
    setListing(true); setMessage(null);
    try {
      const data = await requestJson<{ models: string[] }>('/api/v1/models/list', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: localConfig.baseUrl, apiKey }),
      });
      setModels(data.models);
      if (!localConfig.modelName.trim() && data.models.length) {
        setLocalConfig((current) => ({ ...current, modelName: data.models[0] }));
      }
      setMessage({ tone: 'success', text: `获取到 ${data.models.length} 个可用模型，在「模型名称」中下拉选择。` });
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : '获取模型列表失败。' });
    } finally { setListing(false); }
  };

  return (
    <section className="ac-set-card">
      <div className="ac-set-side">
        <h2><Cpu size={15} /> 模型连接
          <span className={configured ? 'ac-badge success' : 'ac-badge pending'}>
            {configured ? '已配置' : '未配置'}
          </span>
        </h2>
        <p>OpenAI 兼容服务的端点与密钥，在模型服务商控制台获取。B 站视频导入用它把转写稿生成学习笔记；Base URL 带 /v1 与不带均可。</p>
      </div>
      <div className="ac-set-main">
        <form onSubmit={save}>
          <div className="ac-field">
            <label htmlFor="base-url">Base URL</label>
            <input id="base-url" className="ac-input" type="url" value={localConfig.baseUrl} onChange={(event) => setLocalConfig({ ...localConfig, baseUrl: event.target.value })} placeholder="https://api.openai.com/v1" />
          </div>
          <div className="ac-field">
            <label htmlFor="model-api-key">API Key</label>
            <input id="model-api-key" className="ac-input" type="password" autoComplete="new-password" value={localConfig.apiKey} onChange={(event) => setLocalConfig({ ...localConfig, apiKey: event.target.value })} placeholder={config.apiKeyConfigured ? '已配置，输入新 Key 可更换' : 'sk-...'} />
            <p className="ac-help">仅保存在后端数据库，页面只返回掩码。</p>
          </div>
          <div className="ac-field">
            <label htmlFor="model-name">模型名称</label>
            <div className="ac-input-group">
              <input id="model-name" className="ac-input" list="model-name-options" value={localConfig.modelName} onChange={(event) => { setLocalConfig({ ...localConfig, modelName: event.target.value }); setMessage(null); }} placeholder="gpt-4o-mini / deepseek-chat" disabled={listing} />
              <button type="button" className="ac-btn secondary" onClick={() => void fetchModels()} disabled={listing}>
                <ListChecks size={14} />{listing ? '获取中…' : '获取可用模型'}
              </button>
            </div>
            <datalist id="model-name-options">
              {models.map((model) => <option key={model} value={model} />)}
            </datalist>
            <p className="ac-help">先「获取可用模型」再从下拉选择，也可手动输入。</p>
          </div>
          {message && <p className={`tikhub-message ${message.tone}`} role="status">{message.text}</p>}
          <div className="ac-actions">
            <button type="button" className="ac-btn secondary" onClick={() => void saveAndTest()} disabled={testing || saving || !localConfig.modelName.trim()}>
              <PlugZap size={14} />{testing ? '保存并测试中…' : '保存并测试连接'}
            </button>
            <button type="submit" className="ac-btn primary" disabled={saving || testing}>{saving ? '保存中…' : '保存模型配置'}</button>
          </div>
        </form>
      </div>
    </section>
  );
}

function TranscriptionPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true); setMessage(null);
    const ok = await setConfig(localConfig);
    setMessage(ok
      ? { tone: 'success', text: '转写配置已保存。' }
      : { tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    setSaving(false);
  };

  return (
    <section className="ac-set-card">
      <div className="ac-set-side">
        <h2><AudioLines size={15} /> 语音转写
          <span className={config.minimaxConfigured ? 'ac-badge success' : 'ac-badge pending'}>
            {config.minimaxConfigured ? '已配置' : '未配置'}
          </span>
        </h2>
        <p>B 站视频没有 CC 字幕时，下载音频经 MiniMax 云端转写为文稿，再交给模型生成笔记。Token Plan 订阅 Key 以 sk-cp- 开头。</p>
      </div>
      <div className="ac-set-main">
        <form onSubmit={save}>
          <div className="ac-field">
            <label htmlFor="minimax-api-key">MiniMax 转写 Key</label>
            <input id="minimax-api-key" className="ac-input" type="password" autoComplete="new-password" value={localConfig.minimaxApiKey ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, minimaxApiKey: event.target.value })} placeholder={config.minimaxConfigured ? '已配置，输入新 Key 可更换' : 'sk-cp-...'} />
            <p className="ac-help">仅保存在后端数据库，页面只返回掩码。</p>
          </div>
          <div className="ac-field">
            <label htmlFor="minimax-api-base">MiniMax 转写端点</label>
            <input id="minimax-api-base" className="ac-input" value={localConfig.minimaxApiBase ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, minimaxApiBase: event.target.value })} placeholder="https://api.minimax.cn" />
            <p className="ac-help">仅使用自建中转或代理时填写；留空用官方地址，偶发连不上会自动换备用官方域名重试。</p>
          </div>
          {message && <p className={`tikhub-message ${message.tone}`} role="status">{message.text}</p>}
          <div className="ac-actions">
            <button type="submit" className="ac-btn primary" disabled={saving}>{saving ? '保存中…' : '保存转写配置'}</button>
          </div>
        </form>
      </div>
    </section>
  );
}

function GenerationPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true); setMessage(null);
    const ok = await setConfig(localConfig);
    setMessage(ok
      ? { tone: 'success', text: '生成参数已保存。' }
      : { tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    setSaving(false);
  };

  const numberField = (
    id: string, label: string, key: 'llmTemperature' | 'llmMaxTokens' | 'llmTimeoutSeconds' | 'summaryLength',
    hint: string, attrs: { min?: number; max?: number; step?: number },
  ) => (
    <div className="ac-field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className="ac-input" type="number" inputMode="decimal" style={{ maxWidth: 220 }} min={attrs.min} max={attrs.max} step={attrs.step ?? 1}
        value={localConfig[key] ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, [key]: event.target.value })}
        placeholder="默认" />
      <p className="ac-help">{hint}</p>
    </div>
  );

  return (
    <section className="ac-set-card">
      <div className="ac-set-side">
        <h2><SlidersHorizontal size={15} /> 生成参数</h2>
        <p>控制笔记生成与列表摘要的调用参数。数值留空即恢复默认，超出安全范围会被自动夹回。</p>
      </div>
      <div className="ac-set-main">
        <form onSubmit={save}>
          <div className="ac-grid-2">
            {numberField('llm-temperature', '生成温度', 'llmTemperature', '0（精确）~ 2（发散），默认 0.3。', { min: 0, max: 2, step: 0.1 })}
            {numberField('llm-max-tokens', '单次最大输出', 'llmMaxTokens', '默认 512000；更换模型时按其上限调整。', { min: 1, step: 1000 })}
            {numberField('llm-timeout', '请求超时（秒）', 'llmTimeoutSeconds', '默认 300；长视频笔记生成较慢。', { min: 30, max: 1200, step: 10 })}
            {numberField('summary-length', '摘要长度（字）', 'summaryLength', '列表页摘要的截取长度，默认 120。', { min: 20, max: 2000, step: 10 })}
          </div>
          <div className="ac-field">
            <label htmlFor="notes-prompt">视频笔记提示词</label>
            <textarea id="notes-prompt" className="ac-textarea" rows={7} spellCheck={false}
              value={localConfig.notesPrompt ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, notesPrompt: event.target.value })}
              placeholder={'留空使用内置的教科书式笔记模板。\n可用占位符：{title} {uploader} {chapters} {description} {transcript}'} />
            <p className="ac-help">自定义转写稿改写成笔记的提示词模板；占位符以外的花括号需写成 {'{{ }}'}。</p>
          </div>
          {message && <p className={`tikhub-message ${message.tone}`} role="status">{message.text}</p>}
          <div className="ac-actions">
            <button type="submit" className="ac-btn primary" disabled={saving}>{saving ? '保存中…' : '保存生成参数'}</button>
          </div>
        </form>
      </div>
    </section>
  );
}

/** 模型服务：连接、语音转写与生成参数 */
export default function AdminModelSettings() {
  return (
    <div>
      <AdminPageHeader summary={<span>模型服务：连接、语音转写与生成参数</span>} />
      <div className="ac-settings-page"><div className="ac-settings-content">
        <ConnectionPanel />
        <TranscriptionPanel />
        <GenerationPanel />
      </div></div>
    </div>
  );
}
