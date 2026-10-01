import { AlertTriangle, Loader2, X } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 通用确认弹窗:拦截删除等不可逆操作;样式沿用全局 modal 设计,危险色内联避免依赖页面级变量。 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmText = '确认删除',
  cancelText = '取消',
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={() => !busy && onCancel()}>
      <section
        className="config-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
        style={{ width: 'min(420px, 100%)' }}
      >
        <div className="config-modal-header">
          <div>
            <h2 id="confirm-dialog-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertTriangle size={17} style={{ color: 'var(--danger)', flexShrink: 0 }} />
              {title}
            </h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button type="button" className="modal-close" aria-label="关闭确认弹窗" onClick={onCancel} disabled={busy}><X size={17} /></button>
        </div>
        <div className="modal-footer">
          <button type="button" className="secondary-button" onClick={onCancel} disabled={busy}>{cancelText}</button>
          <button type="button" className="primary-button" style={{ background: 'var(--danger)' }} onClick={onConfirm} disabled={busy}>
            {busy ? <><Loader2 size={14} className="animate-spin" />删除中</> : confirmText}
          </button>
        </div>
      </section>
    </div>
  );
}
