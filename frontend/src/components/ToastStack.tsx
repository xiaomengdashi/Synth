import { useEffect, useState } from 'react';
import { X, CheckCircle2, AlertCircle } from 'lucide-react';
import { useAppStore } from '../features/app/store/useAppStore';

function ToastItem({
  id,
  title,
  tone,
}: {
  id: string;
  title: string;
  tone: 'success' | 'error';
}) {
  const removeToast = useAppStore((state) => state.removeToast);
  const [leaving, setLeaving] = useState(false);

  const dismiss = () => {
    if (leaving) return;
    setLeaving(true);
    window.setTimeout(() => removeToast(id), 170);
  };

  useEffect(() => {
    const timer = window.setTimeout(dismiss, 2600);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return (
    <div className={leaving ? 'toast-item toast-leaving' : 'toast-item'}>
      <span className={tone === 'success' ? 'toast-icon success' : 'toast-icon error'}>
        {tone === 'success' ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
      </span>
      <span>{title}</span>
      <button type="button" onClick={dismiss} aria-label="关闭提示">
        <X size={15} />
      </button>
    </div>
  );
}

/** 全局操作反馈浮层,前台与后台布局共用。 */
export default function ToastStack() {
  const toasts = useAppStore((state) => state.toasts);

  return (
    <div className="toast-stack">
      {toasts.map((toast) => <ToastItem key={toast.id} {...toast} />)}
    </div>
  );
}
