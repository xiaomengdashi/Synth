import { useEffect, useState } from 'react';
import { Cpu, Globe2, KeyRound } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import type { AppConfig } from '../../config/types';

export default function SettingsModelPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState<AppConfig>(config);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const displayKey = (key: string) => key.length > 6 ? `${key.slice(0, 4)}...${key.slice(-2)}` : key;
  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setConfig({ ...localConfig, apiKey: localConfig.apiKey.includes('...') ? config.apiKey : localConfig.apiKey });
  };

  return (
    <div className="settings-tab-panel">
      <form className="settings-panel settings-form-panel" onSubmit={save}>
        <h2><Cpu size={16} /> 连接参数</h2>
        <p>OpenAI 兼容服务的参数在模型服务商控制台获取。当前内容导入不调用模型，参数留作后续功能启用。</p>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="base-url"><Globe2 size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> Base URL</label>
            <input id="base-url" type="url" value={localConfig.baseUrl} onChange={(event) => setLocalConfig({ ...localConfig, baseUrl: event.target.value })} placeholder="https://api.openai.com/v1" />
          </div>
          <div className="form-field">
            <label htmlFor="api-key"><KeyRound size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> API Key</label>
            <input id="api-key" type="text" value={localConfig.apiKey === config.apiKey && config.apiKey ? displayKey(config.apiKey) : localConfig.apiKey} onFocus={() => { if (localConfig.apiKey === config.apiKey) setLocalConfig({ ...localConfig, apiKey: '' }); }} onChange={(event) => setLocalConfig({ ...localConfig, apiKey: event.target.value })} placeholder="sk-..." />
          </div>
          <div className="form-field full">
            <label htmlFor="model-name"><Cpu size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> 模型名称</label>
            <input id="model-name" value={localConfig.modelName} onChange={(event) => setLocalConfig({ ...localConfig, modelName: event.target.value })} placeholder="gpt-4o-mini / deepseek-chat" />
          </div>
        </div>
        <div className="modal-footer">
          <button type="submit" className="primary-button">保存模型配置</button>
        </div>
      </form>
    </div>
  );
}
