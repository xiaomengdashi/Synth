import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps { children: ReactNode }
interface ErrorBoundaryState { hasError: boolean }

// vite 动态 import 失败在各内核的报错形态(网络抖动/代理闪断/发版后旧 chunk 被清理)
const CHUNK_ERROR_PATTERN = /dynamically imported module|importing a module script failed|errorLoadingDynamicUrl|failed to fetch dynamically/i;

/** 全局错误边界:任一路由渲染崩溃时给出恢复入口,避免整页白屏。 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // chunk 加载失败说明是环境性问题而非渲染逻辑错误:自动整页刷新一次。
    // 10 秒内只刷一次,防止异常环境陷入刷新循环。
    const message = String(error?.message ?? error);
    if (CHUNK_ERROR_PATTERN.test(message)) {
      const marker = 'chunkReloadAt';
      const last = Number(sessionStorage.getItem(marker) || 0);
      if (Date.now() - last > 10_000) {
        sessionStorage.setItem(marker, String(Date.now()));
        window.location.reload();
        return;
      }
    }
    console.error('Unhandled render error', error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div style={{ minHeight: '60vh', display: 'grid', placeItems: 'center', padding: 24 }}>
        <div style={{ maxWidth: 420, textAlign: 'center' }}>
          <h1 style={{ fontSize: 22, margin: '0 0 10px' }}>页面出错了</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13, lineHeight: 1.8, margin: '0 0 18px' }}>渲染时发生意外错误，刷新或回到首页通常可以恢复。</p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <button type="button" className="secondary-button" onClick={() => window.location.reload()}>刷新页面</button>
            <a className="primary-button" href="/" style={{ textDecoration: 'none' }}>返回首页</a>
          </div>
        </div>
      </div>
    );
  }
}
