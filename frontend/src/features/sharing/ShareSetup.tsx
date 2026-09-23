import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Copy, Share2, Smartphone } from 'lucide-react';

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
    <div className="share-page share-setup-page">
      <div className="eyebrow">Save from anywhere you read</div>
      <h1>在手机里看到，<br />顺手存到这里。</h1>
      <p className="share-lede">给 iPhone 添加一次快捷指令，以后分享文章时，选择「保存到 SynthAI」就好。</p>
      <div className="share-flow"><span><Share2 size={16} /> X / 微信分享</span><ArrowRight size={15} /><span><Smartphone size={16} /> 保存到 SynthAI</span><ArrowRight size={15} /><span>文章库</span></div>

      <section className="share-setup-step">
        <span className="share-step-number">01</span><div>
          <h2>先让手机打开这个网站</h2>
          <p>在 iPhone 的 Safari 中打开下面的地址。使用电脑运行的版本时，手机和电脑需连接同一 Wi-Fi，电脑需保持开机、服务运行。</p>
          <label className="share-input-label" htmlFor="mobile-site-url">iPhone 可访问的网站地址</label>
          <div className="share-address-row"><input id="mobile-site-url" type="url" value={address} onChange={(event) => { setAddress(event.target.value); setCopyMessage(''); }} spellCheck={false} /><button type="button" className="secondary-button" disabled={!origin} onClick={() => void copyAddress()}><Copy size={14} />复制</button></div>
          <p className={addressError ? 'share-inline-notice' : 'form-help'} role="status">{addressError || copyMessage || '快捷指令中的网站地址应与这里一致。'}</p>
        </div>
      </section>
      <section className="share-setup-step">
        <span className="share-step-number">02</span><div>
          <h2>添加「保存到 SynthAI」</h2>
          <p>{shortcutIcloudUrl ? '在 iPhone 上打开 iCloud 快捷指令链接，添加时，将网站地址设为上一步已能打开的地址。首次运行时，允许它打开该网站。' : '当前站点还没有配置 iCloud 一键安装链接。你仍然可以按下方说明手动创建快捷指令，效果相同。'}</p>
          {shortcutIcloudUrl ? (
            <>
              <a className="primary-button share-download" href={shortcutIcloudUrl} target="_blank" rel="noreferrer">打开 iCloud 快捷指令</a>
              <p className="form-help">如果 Safari 没有直接跳转到快捷指令 App，可点右上角“在浏览器中打开”，或复制到 Safari 重新打开。</p>
            </>
          ) : (
            <p className="share-inline-notice">未配置一键安装链接时，建议先用下方“手动创建快捷指令”完成设置。</p>
          )}
        </div>
      </section>
      <section className="share-setup-step">
        <span className="share-step-number">03</span><div>
          <h2>回到 X 或微信，分享第一篇文章</h2>
          <p>打开 X 帖子、X 长文或微信公众号文章，点击分享 → “通过其他方式分享” → 在系统分享菜单中选择「保存到 SynthAI」。网站会自动获取链接、抓取内容，并打开保存好的文章。</p>
          <p className="form-help">如果没看到入口，请打开快捷指令的详细信息，开启“在共享表单中显示”。入口名称可能随 iOS、X 和微信版本略有不同。</p>
        </div>
      </section>
      <details className="share-help"><summary>{shortcutIcloudUrl ? 'iCloud 链接打不开？手动创建快捷指令' : '手动创建快捷指令'}</summary>
        <ol><li>新建快捷指令，命名为「保存到 SynthAI」，开启“在共享表单中显示”，接收 URL 和文本。</li><li>添加“URL 编码”，输入选择“快捷指令输入”，操作选择“编码”。</li><li>添加“文本”，输入下方前缀，再插入上一步“URL 编码”的结果变量。</li><li>添加“打开 URL”，输入选择上一步的文本。</li></ol>
        <code>{origin || 'https://你的网站地址'}/share?text=</code>
      </details>
      <p className="share-setup-note">分享只会传递文章链接，不会传递你在 App 内的登录信息。X 长文仍需要电脑上的 X 抓取登录态可用；微信文章如果触发安全验证，则会按你当前的微信抓取配置处理；外出使用需另行配置手机可访问的服务地址。</p>
      <div className="share-footer-links"><Link to="/">返回首页</Link><Link to="/share">手动试用导入 <ArrowRight size={14} /></Link></div>
    </div>
  );
}
