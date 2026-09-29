import { useEffect } from 'react';
import { ArrowRight, Bird, CheckCircle2, Cpu, Smartphone } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';

export default function AdminSettings() {
  const { config, fetchConfig } = useAppStore();

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);

  const modelReady = Boolean(config.baseUrl || config.modelName || config.apiKey);
  const tikhubReady = Boolean(config.tikhubConfigured);

  return (
    <div>
      <AdminPageHeader
        eyebrow="Settings / 04"
        title="系统配置"
        description="选择一个配置模块进入独立页面，避免不同服务的设置互相干扰。"
      />
      <section className="admin-overview-grid settings-overview-grid">
        <Link to="/share/setup" className="overview-link-panel">
          <span className="overview-panel-icon"><Smartphone size={19} /></span>
          <div><span className="eyebrow">iPhone / Share</span><h2>手机分享导入</h2><p>从 X 或微信文章的分享菜单直接保存内容到 SynthAI。</p><small className="config-status">设置快捷指令</small></div>
          <ArrowRight size={17} />
        </Link>
        <Link to="/admin/settings/model" className="overview-link-panel">
          <span className="overview-panel-icon"><Cpu size={19} /></span>
          <div>
            <span className="eyebrow">Model / 01</span>
            <h2>模型服务</h2>
            <p>保存 Base URL、API Key 和模型名称，暂不启用模型请求。</p>
            <small className={modelReady ? 'config-status ready' : 'config-status'}><CheckCircle2 size={13} />{modelReady ? '参数已保存' : '待设置'}</small>
          </div>
          <ArrowRight size={17} />
        </Link>
        <Link to="/admin/settings/tikhub" className="overview-link-panel">
          <span className="overview-panel-icon"><Bird size={19} /></span>
          <div>
            <span className="eyebrow">TikHub / 02</span>
            <h2>TikHub 数据服务</h2>
            <p>管理 Key、余额与用量，查询抖音、X、B站、微信等多平台数据。</p>
            <small className={tikhubReady ? 'config-status ready' : 'config-status'}><CheckCircle2 size={13} />{tikhubReady ? '已配置' : '必填配置'}</small>
          </div>
          <ArrowRight size={17} />
        </Link>
      </section>
    </div>
  );
}
