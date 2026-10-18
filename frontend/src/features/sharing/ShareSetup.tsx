import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Copy, Share2, Smartphone } from 'lucide-react';

export default function ShareSetup() {
  const [address, setAddress] = useState(window.location.origin);
  const [copyMessage, setCopyMessage] = useState('');
  const shortcutIcloudUrl = (import.meta.env.VITE_SHARE_SHORTCUT_ICLOUD_URL || '').trim();
  let origin = '';
  let addressError = '';
  try {
    const url = new URL(address);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error();
    if (['localhost', '127.0.0.1', '[::1]', '0.0.0.0'].includes(url.hostname)) {
      addressError = '这是电脑本机地址，iPhone 无法使用。请填写电脑的局域网地址，或手机可访问的网站域名。';
    } else origin = url.origin;
  } catch { addressError = '请填写完整的网站地址，例如 http://192.168.1.10:5173。'; }
  const copyAddress = async () => {
    try { await navigator.clipboard.writeText(origin); setCopyMessage('已复制网站地址'); }
    catch { setCopyMessage('请长按或选中上方地址复制'); }
  };

  return (
    <div className="ac-stack">
      <section className="ac-card">
        <div className="ac-card-head">
          <h2 className="ac-card-title"><Smartphone size={15} /> 分享流程</h2>
        </div>
        <div className="ac-card-body">
          <p className="ac-card-desc">给 iPhone 添加一次「保存到 SynthAI」快捷指令，之后看到想保存的文章或视频，直接从分享菜单保存进文章库。</p>
          <div className="share-flow" style={{ margin: 0, padding: 0, borderBottom: 0 }}>
            <span><Share2 size={16} /> 文章 / 视频分享</span><ArrowRight size={15} />
            <span><Smartphone size={16} /> 保存到 SynthAI</span><ArrowRight size={15} />
            <span>文章库</span>
          </div>
        </div>
        <div className="ac-card-foot" style={{ justifyContent: 'flex-start' }}>
          <Link to="/admin/share" className="ac-btn secondary"><ArrowLeft size={14} /> 返回配置中心</Link>
          <Link to="/share" className="ac-btn secondary">手动试用导入 <ArrowRight size={14} /></Link>
        </div>
      </section>

      <section className="ac-card">
        <div className="ac-card-head">
          <h2 className="ac-card-title">第一步 · 先让手机打开这个网站</h2>
        </div>
        <div className="ac-card-body">
          <p className="ac-card-desc">在 iPhone 的 Safari 中打开下面的地址，并访问一次后台完成登录——导入功能只对已登录的站长开放，登录一次后分享导入即可自动可用。使用电脑运行的版本时，手机和电脑需连接同一 Wi-Fi，电脑需保持开机、服务运行。</p>
          <label className="share-input-label" htmlFor="mobile-site-url">iPhone 可访问的网站地址</label>
          <div className="share-address-row">
            <input id="mobile-site-url" className="ac-input" type="url" value={address} onChange={(event) => { setAddress(event.target.value); setCopyMessage(''); }} spellCheck={false} />
            <button type="button" className="ac-btn secondary" disabled={!origin} onClick={() => void copyAddress()}><Copy size={14} />复制</button>
          </div>
          <p className={addressError ? 'share-inline-notice' : 'ac-help'} role="status" style={{ marginTop: 10 }}>{addressError || copyMessage || '快捷指令中的网站地址应与这里一致。'}</p>
        </div>
      </section>

      <section className="ac-card">
        <div className="ac-card-head">
          <h2 className="ac-card-title">第二步 · 添加「保存到 SynthAI」</h2>
        </div>
        <div className="ac-card-body">
          <p className="ac-card-desc" style={{ marginBottom: 0 }}>{shortcutIcloudUrl ? '在 iPhone 上打开 iCloud 快捷指令链接，添加时，将网站地址设为上一步已能打开的地址。首次运行时，允许它打开该网站。' : '暂未提供一键安装链接，请按下方说明手动创建快捷指令。'}</p>
          {shortcutIcloudUrl && (
            <div className="ac-actions" style={{ justifyContent: 'flex-start' }}>
              <a className="ac-btn primary" href={shortcutIcloudUrl} target="_blank" rel="noreferrer">打开 iCloud 快捷指令 <ArrowRight size={14} /></a>
            </div>
          )}
        </div>
      </section>

      <section className="ac-card">
        <div className="ac-card-head">
          <h2 className="ac-card-title">第三步 · 分享第一篇文章或视频</h2>
        </div>
        <div className="ac-card-body">
          <p className="ac-card-desc">打开支持的文章或视频，点击分享 → “通过其他方式分享” → 在系统分享菜单中选择「保存到 SynthAI」。网站会自动获取链接、抓取内容，并打开保存好的文章。</p>
          <p className="ac-help" style={{ marginBottom: 0 }}>如果没看到入口，请打开快捷指令的详细信息，开启“在共享表单中显示”。入口名称可能随 iOS、X 和微信版本略有不同。</p>
        </div>
      </section>

      <details className="ac-card share-help">
        <summary style={{ padding: '14px 18px', fontWeight: 600, cursor: 'pointer' }}>{shortcutIcloudUrl ? 'iCloud 链接打不开？手动创建快捷指令' : '手动创建快捷指令'}</summary>
        <div style={{ padding: '0 18px 16px' }}>
          <ol style={{ margin: '0 0 14px', paddingLeft: 20 }}><li>新建快捷指令，命名为「保存到 SynthAI」，开启“在共享表单中显示”，接收 URL 和文本。</li><li>添加“URL 编码”，输入选择“快捷指令输入”，操作选择“编码”。</li><li>添加“文本”，输入下方前缀，再插入上一步“URL 编码”的结果变量。</li><li>添加“打开 URL”，输入选择上一步的文本。</li></ol>
          <code>{origin || 'https://你的网站地址'}/share?text=</code>
        </div>
      </details>

      <p className="ac-help">分享只会传递文章链接，不会传递你在 App 内的登录信息；外出使用需保证手机可访问的服务地址在线。</p>
    </div>
  );
}
