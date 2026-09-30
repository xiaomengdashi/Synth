import { useCallback, useEffect, useRef, useState } from 'react';
import { Bird, Cpu, KeyRound, ListChecks, PlugZap, RefreshCw, Wallet } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import { dateTime, money, requestJson } from '../../tikhub/client';
import { adminFetch, saveAdminToken } from '../../../utils/adminAuth';
import type { Account, KeyStatus } from '../../tikhub/types';
import AdminPageHeader from '../components/AdminPageHeader';

function ModelPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [models, setModels] = useState<string[]>([]);
  const [listing, setListing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modelMessage, setModelMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  // 表单里的 Key 是掩码时不下发，后端改用已保存的真实 Key
  const effectiveApiKey = localConfig.apiKey.includes('•')
    ? undefined : (localConfig.apiKey.trim() || undefined);

  const persistConfig = () => setConfig(localConfig);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true); setModelMessage(null);
    const ok = await persistConfig();
    setModelMessage(ok
      ? { tone: 'success', text: '模型配置已保存。' }
      : { tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    setSaving(false);
  };

  const saveAndTest = async () => {
    setTesting(true); setModelMessage(null);
    const saved = await persistConfig();
    if (!saved) {
      setModelMessage({ tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
      setTesting(false);
      return;
    }
    try {
      const data = await requestJson<{ ok: boolean; latency_ms: number }>('/api/v1/models/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: localConfig.baseUrl, apiKey: effectiveApiKey, model: localConfig.modelName }),
      });
      setModelMessage({ tone: 'success', text: `配置已保存，模型「${localConfig.modelName}」连接成功，响应 ${data.latency_ms} ms。` });
    } catch (e) {
      setModelMessage({ tone: 'error', text: `配置已保存，但连接测试失败：${e instanceof Error ? e.message : '未知错误'}` });
    } finally { setTesting(false); }
  };

  const fetchModels = async () => {
    setListing(true); setModelMessage(null);
    try {
      const data = await requestJson<{ models: string[] }>('/api/v1/models/list', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: localConfig.baseUrl, apiKey: effectiveApiKey }),
      });
      setModels(data.models);
      if (!localConfig.modelName.trim() && data.models.length) {
        setLocalConfig((current) => ({ ...current, modelName: data.models[0] }));
      }
      setModelMessage({ tone: 'success', text: `获取到 ${data.models.length} 个可用模型，在「模型名称」中下拉选择。` });
    } catch (e) {
      setModelMessage({ tone: 'error', text: e instanceof Error ? e.message : '获取模型列表失败。' });
    } finally { setListing(false); }
  };

  return (
    <div className="ac-stack">
      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><Cpu size={15} /> 连接参数</h2>
          <p>OpenAI 兼容服务的参数在模型服务商控制台获取。当前内容导入不调用模型，参数留作后续功能启用。</p>
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
              <p className="ac-help">Key 仅保存在后端数据库；页面读取时只返回掩码。</p>
            </div>
            <div className="ac-field">
              <label htmlFor="model-name">模型名称</label>
              <div className="ac-input-group">
                <input id="model-name" className="ac-input" list="model-name-options" value={localConfig.modelName} onChange={(event) => { setLocalConfig({ ...localConfig, modelName: event.target.value }); setModelMessage(null); }} placeholder="gpt-4o-mini / deepseek-chat" disabled={listing} />
                <button type="button" className="ac-btn secondary" onClick={() => void fetchModels()} disabled={listing}>
                  <ListChecks size={14} />{listing ? '获取中…' : '获取可用模型'}
                </button>
              </div>
              <datalist id="model-name-options">
                {models.map((model) => <option key={model} value={model} />)}
              </datalist>
              <p className="ac-help">先「获取可用模型」，再从下拉中选择；也可以直接手动输入。</p>
            </div>
            {modelMessage && <p className={`tikhub-message ${modelMessage.tone}`} role="status">{modelMessage.text}</p>}
            <div className="ac-actions">
              <button type="button" className="ac-btn secondary" onClick={() => void saveAndTest()} disabled={testing || saving || !localConfig.modelName.trim()}>
                <PlugZap size={14} />{testing ? '保存并测试中…' : '保存并测试连接'}
              </button>
              <button type="submit" className="ac-btn primary" disabled={saving || testing}>{saving ? '保存中…' : '保存模型配置'}</button>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}

/** 模型服务：LLM 端点与密钥配置 */
export default function AdminModelSettings() {
  return (
    <div>
      <AdminPageHeader summary={<span>模型服务：LLM 端点与密钥配置</span>} />
      <div className="ac-settings-page"><div className="ac-settings-content">
        <ModelPanel />
      </div></div>
    </div>
  );
}
