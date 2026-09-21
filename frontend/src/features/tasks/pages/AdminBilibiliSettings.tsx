import { useEffect, useState } from 'react';
import { ArrowLeft, Video } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';

export default function AdminBilibiliSettings() {
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
      <AdminPageHeader eyebrow="Settings / 04 / Bilibili" title="Bilibili 抓取" description="登录态可以提升字幕与视频信息的抓取成功率。" actions={<Link to="/admin/settings" className="secondary-button"><ArrowLeft size={14} /> 配置总览</Link>} />
      <form className="settings-layout" onSubmit={save}>
        <section className="settings-panel">
          <h2><Video size={16} /> 登录态</h2>
          <p>仅用于本地抓取 Bilibili 内容，不会展示在文章页面。</p>
          <div className="form-grid">
            <div className="form-field full"><label htmlFor="sessdata">SESSDATA</label><input id="sessdata" type="password" value={localConfig.biliSessdata || ''} onChange={(event) => setLocalConfig({ ...localConfig, biliSessdata: event.target.value })} placeholder="浏览器 Cookie 中的 SESSDATA" /></div>
            <div className="form-field"><label htmlFor="bili-jct">bili_jct</label><input id="bili-jct" type="password" value={localConfig.biliJct || ''} onChange={(event) => setLocalConfig({ ...localConfig, biliJct: event.target.value })} placeholder="可选" /></div>
            <div className="form-field"><label htmlFor="buvid3">buvid3</label><input id="buvid3" type="password" value={localConfig.biliBuvid3 || ''} onChange={(event) => setLocalConfig({ ...localConfig, biliBuvid3: event.target.value })} placeholder="可选" /></div>
          </div>
          <div className="modal-footer"><button type="submit" className="primary-button">保存 B站配置</button></div>
        </section>
      </form>
    </div>
  );
}
