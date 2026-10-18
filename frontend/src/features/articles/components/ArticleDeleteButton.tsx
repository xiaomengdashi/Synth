import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { getAdminToken } from '../../../utils/adminAuth';
import { useAppStore } from '../../app/store/useAppStore';

export default function ArticleDeleteButton({ articleId, title }: { articleId: string; title: string }) {
  const navigate = useNavigate();
  const deleteArticle = useAppStore(state => state.deleteArticle);
  const [verifiedToken, setVerifiedToken] = useState('');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const deletingRef = useRef(false);

  useEffect(() => {
    let controller: AbortController | undefined;
    const verify = async () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      const token = getAdminToken();
      setVerifiedToken('');
      if (!token) {
        setConfirmOpen(false);
        return;
      }
      try {
        const response = await fetch('/api/v1/admin-auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
          signal: current.signal,
        });
        if (current.signal.aborted) return;
        if (response.ok && getAdminToken() === token) setVerifiedToken(token);
        else setConfirmOpen(false);
      } catch {
        if (!current.signal.aborted) setConfirmOpen(false);
      }
    };
    const refresh = () => { void verify(); };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'synthai_admin_token' || event.key === null) refresh();
    };
    refresh();
    window.addEventListener('focus', refresh);
    window.addEventListener('storage', onStorage);
    return () => {
      controller?.abort();
      window.removeEventListener('focus', refresh);
      window.removeEventListener('storage', onStorage);
    };
  }, [articleId]);

  const confirmDelete = async () => {
    if (deletingRef.current) return;
    if (!verifiedToken || getAdminToken() !== verifiedToken) {
      setVerifiedToken('');
      setConfirmOpen(false);
      return;
    }
    deletingRef.current = true;
    setBusy(true);
    try {
      if (await deleteArticle(articleId)) navigate('/articles', { replace: true });
    } finally {
      deletingRef.current = false;
      setBusy(false);
    }
  };

  return <>
    {verifiedToken ? (
      <button type="button" className="reader-tool danger" disabled={busy} onClick={() => setConfirmOpen(true)}>
        <Trash2 size={13} />删除文章
      </button>
    ) : null}
    <ConfirmDialog
      open={confirmOpen && Boolean(verifiedToken)}
      title="删除文章"
      description={`确定删除「${title}」？关联笔记也会删除，此操作不可恢复。`}
      confirmText="删除"
      busy={busy}
      onCancel={() => { if (!deletingRef.current) setConfirmOpen(false); }}
      onConfirm={() => void confirmDelete()}
    />
  </>;
}
