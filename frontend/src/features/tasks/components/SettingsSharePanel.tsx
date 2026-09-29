import { ArrowRight, Smartphone } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function SettingsSharePanel() {
  return (
    <div className="settings-tab-panel">
      <section className="settings-panel settings-form-panel">
        <h2><Smartphone size={16} /> iPhone 分享导入</h2>
        <p>安装「保存到 SynthAI」快捷指令后，在手机上的 X 或微信里看到好文章，直接从分享菜单保存进文章库，无需打开电脑。</p>
        <div className="share-flow"><span>分享菜单</span><ArrowRight size={15} /><span>保存到 SynthAI</span><ArrowRight size={15} /><span>文章库</span></div>
        <p className="form-help">设置包含网站地址确认、iCloud 一键安装（可选）与手动创建指引，在独立页面完成。</p>
        <div className="modal-footer">
          <Link to="/share/setup" className="primary-button">打开分享设置 <ArrowRight size={14} /></Link>
        </div>
      </section>
    </div>
  );
}
