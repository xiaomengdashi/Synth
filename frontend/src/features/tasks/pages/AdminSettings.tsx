import { useEffect, useState } from 'react';
import { ArrowRight, Bird, CheckCircle2, Cpu, Smartphone } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import { money, requestJson } from '../../tikhub/client';
import type { Account } from '../../tikhub/types';

export default function AdminSettings() {
  const { config, fetchConfig } = useAppStore();
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => {
    // 余额摘要属于展示性信息，失败时静默降级为仅状态徽章
    void requestJson<Account>('/api/v1/tikhub/account').then(setAccount).catch(() => setAccount(null));
  }, []);

  const modelReady = Boolean(config.baseUrl || config.modelName || config.apiKey);
  const tikhubReady = Boolean(config.tikhubConfigured);
  const usage = account?.daily_usage;

  return (
    <div>
      <AdminPageHeader
        eyebrow="Settings / 04"
        title="系统配置"
        description="内容抓取依赖 TikHub 接口；模型服务与手机分享导入为可选功能。"
      />
      <section className="admin-overview-grid settings-overview-grid">
        <Link to="/admin/settings/tikhub" className="overview-link-panel">
          <span className="overview-panel-icon"><Bird size={19} /></span>
          <div>
            <span className="eyebrow">数据抓取 · 必填</span>
            <h2>TikHub 数据服务</h2>
            <p>X 推文与长文、公众号文章、Bilibili 视频全部经 TikHub 获取，同时提供多平台数据查询。</p>
            {tikhubReady && account?.user ? (
              <small className="config-status ready">
                <CheckCircle2 size={13} />已配置 · 余额 {money(account.user.balance)} · 今日 {money(usage?.usage, 4)}
              </small>
            ) : (
              <small className="config-status"><CheckCircle2 size={13} />{tikhubReady ? '已配置' : '未配置，抓取不可用'}</small>
            )}
          </div>
          <ArrowRight size={17} />
        </Link>
        <Link to="/admin/settings/model" className="overview-link-panel">
          <span className="overview-panel-icon"><Cpu size={19} /></span>
          <div>
            <span className="eyebrow">AI 模型 · 未启用</span>
            <h2>模型服务</h2>
            <p>保存 Base URL、API Key 和模型名称。当前导入流程不调用模型，参数留作后续启用。</p>
            <small className={modelReady ? 'config-status ready' : 'config-status'}><CheckCircle2 size={13} />{modelReady ? '参数已保存' : '未设置'}</small>
          </div>
          <ArrowRight size={17} />
        </Link>
        <Link to="/admin/settings/share" className="overview-link-panel">
          <span className="overview-panel-icon"><Smartphone size={19} /></span>
          <div>
            <span className="eyebrow">移动端 · 可选功能</span>
            <h2>手机分享导入</h2>
            <p>安装 iPhone 快捷指令后，在 X 或微信的分享菜单里把链接一键保存到 SynthAI。</p>
            <small className="config-status">设置快捷指令</small>
          </div>
          <ArrowRight size={17} />
        </Link>
      </section>
    </div>
  );
}
