import type { ReactNode } from 'react';

/**
 * Admin 页面级动作条。页面标题与层级已由顶部面包屑表达，
 * 这里只承载与当前页面相关的操作按钮。
 */
export default function AdminPageHeader({ actions }: { eyebrow?: string; title?: string; description?: string; actions?: ReactNode }) {
  if (!actions) return null;
  return (
    <section className="admin-top admin-top-actions-only">
      {actions ? <div className="admin-top-actions">{actions}</div> : null}
    </section>
  );
}
