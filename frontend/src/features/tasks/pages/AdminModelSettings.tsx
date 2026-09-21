import { useEffect, useState } from 'react';
import { Cpu, Globe2, KeyRound, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import type { AppConfig } from '../../config/types';

export default function AdminModelSettings() {
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
    <div>
      <AdminPageHeader eyebrow="Settings / 04 / Model" title="模型服务" description="保留 OpenAI 兼容服务参数，当前内容导入流程暂不调用大模型。" actions={<Link to="/admin/settings" className="secondary-button"><ArrowLeft size={14} /> 配置总览</Link>} />
      <form className="settings-layout" onSubmit={save}>
        <section className="settings-panel settings-form-panel">
          <h2><Cpu size={16} /> 模型连接</h2>
          <p>暂时保留模型参数设置；当前导入流程不会调用大模型。</p>
          <div className="form-grid">
            <div className="form-field"><label htmlFor="base-url"><Globe2 size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> Base URL</label><input id="base-url" type="url" value={localConfig.baseUrl} onChange={(event) => setLocalConfig({ ...localConfig, baseUrl: event.target.value })} placeholder="https://api.openai.com/v1" /></div>
            <div className="form-field"><label htmlFor="api-key"><KeyRound size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> API Key</label><input id="api-key" type="text" value={localConfig.apiKey === config.apiKey && config.apiKey ? displayKey(config.apiKey) : localConfig.apiKey} onFocus={() => { if (localConfig.apiKey === config.apiKey) setLocalConfig({ ...localConfig, apiKey: '' }); }} onChange={(event) => setLocalConfig({ ...localConfig, apiKey: event.target.value })} placeholder="sk-..." /></div>
            <div className="form-field full"><label htmlFor="model-name"><Cpu size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} /> 模型名称</label><input id="model-name" value={localConfig.modelName} onChange={(event) => setLocalConfig({ ...localConfig, modelName: event.target.value })} placeholder="gpt-4o-mini / deepseek-chat" /><p className="form-help">当前仅保存参数，暂不请求模型服务。</p></div>
          </div>
          <div className="verify-row"><p>模型服务暂未启用，保存的参数不会参与文章抓取或内容整理。</p><span className="text-link">暂未启用</span></div>
          <div className="modal-footer"><button type="submit" className="primary-button">保存模型配置</button></div>
        </section>
      </form>
    </div>
  );
}
