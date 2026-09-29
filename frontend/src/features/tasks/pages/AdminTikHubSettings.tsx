import { useEffect, useState } from 'react';
import { ArrowLeft, Bird } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';

export default function AdminTikHubSettings() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setConfig(localConfig);
  };

  return (
    <div>
      <AdminPageHeader eyebrow="Settings / 04 / TikHub" title="TikHub 抓取" description="配置 TikHub API Token 后，X/Twitter 推文与长文将通过第三方接口获取，无需本机登录态。" actions={<Link to="/admin/settings" className="secondary-button"><ArrowLeft size={14} /> 配置总览</Link>} />
      <form className="settings-layout" onSubmit={save}>
        <section className="settings-panel">
          <h2><Bird size={16} /> API Token</h2>
          <p>在 <a href="https://user.tikhub.io" target="_blank" rel="noreferrer">user.tikhub.io</a> 控制台创建 Token 后填入此处。未配置或余额不足时，自动回退到镜像接口和本机 twitter-cli。</p>
          <div className="form-grid">
            <div className="form-field full"><label htmlFor="tikhub-key">TikHub API Token</label><input id="tikhub-key" type="password" value={localConfig.tikhubApiKey || ''} onChange={(event) => setLocalConfig({ ...localConfig, tikhubApiKey: event.target.value })} placeholder="在 TikHub 用户控制台创建" /></div>
          </div>
          <div className="modal-footer"><button type="submit" className="primary-button">保存 TikHub 配置</button></div>
        </section>
      </form>
    </div>
  );
}
