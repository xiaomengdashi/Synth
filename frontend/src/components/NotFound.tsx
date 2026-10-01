import { Link } from 'react-router-dom';

/** 404 兜底页:前台与后台的未知路由共用。 */
export default function NotFound() {
  return (
    <div style={{ minHeight: '60vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: 'center' }}>
        <h1 style={{ fontSize: 44, letterSpacing: '-.04em', margin: '0 0 8px' }}>404</h1>
        <p style={{ color: 'var(--muted)', fontSize: 13, lineHeight: 1.8, margin: '0 0 18px' }}>这个地址不存在，可能已被删除或从未创建。</p>
        <Link className="primary-button" to="/" style={{ textDecoration: 'none' }}>返回首页</Link>
      </div>
    </div>
  );
}
