import { useEffect } from 'react';
import { X, CheckCircle2, AlertCircle } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
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

  useEffect(() => {
    const timer = window.setTimeout(() => removeToast(id), 2600);
    return () => window.clearTimeout(timer);
  }, [id, removeToast]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.98 }}
      className="toast-item"
    >
      <span className={tone === 'success' ? 'toast-icon success' : 'toast-icon error'}>
        {tone === 'success' ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
      </span>
      <span>{title}</span>
      <button type="button" onClick={() => removeToast(id)} aria-label="关闭提示">
        <X size={15} />
      </button>
    </motion.div>
  );
}

/** 全局操作反馈浮层,前台与后台布局共用。 */
export default function ToastStack() {
  const toasts = useAppStore((state) => state.toasts);

  return (
    <div className="toast-stack">
      <AnimatePresence>
        {toasts.map((toast) => <ToastItem key={toast.id} {...toast} />)}
      </AnimatePresence>
    </div>
  );
}
