import type { ReactNode } from 'react';

/**
 * 后台页面的信息条:左侧页面级摘要,右侧页面级动作。
 * 页面位置由顶栏面包屑表达,这里不再重复标题。
 */
export default function AdminPageHeader({ summary, actions }: { summary?: ReactNode; actions?: ReactNode }) {
  if (!summary && !actions) return null;
  return (
    <section className="ac-pagebar">
      {summary ? <div className="ac-pagebar-summary">{summary}</div> : null}
      {actions ? <div className="ac-pagebar-actions">{actions}</div> : null}
    </section>
  );
}
