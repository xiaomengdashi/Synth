import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import ConfirmDialog from '../../../components/ConfirmDialog';
import useVerifiedAdminToken from '../../../hooks/useVerifiedAdminToken';
import { getAdminToken } from '../../../utils/adminAuth';
import { useAppStore } from '../../app/store/useAppStore';

export default function ArticleDeleteButton({ articleId, title }: { articleId: string; title: string }) {
  const navigate = useNavigate();
  const deleteArticle = useAppStore(state => state.deleteArticle);
  const { status: adminStatus, token: verifiedToken } = useVerifiedAdminToken();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const deletingRef = useRef(false);
  const verified = adminStatus === 'verified';

  const confirmDelete = async () => {
    if (deletingRef.current) return;
    if (!verifiedToken || getAdminToken() !== verifiedToken) {
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
    {verified ? (
      <button type="button" className="reader-tool danger" disabled={busy} onClick={() => setConfirmOpen(true)}>
        <Trash2 size={13} />删除文章
      </button>
    ) : null}
    <ConfirmDialog
      open={confirmOpen && verified}
      title="删除文章"
      description={`确定删除「${title}」？关联笔记也会删除，此操作不可恢复。`}
      confirmText="删除"
      busy={busy}
      onCancel={() => { if (!deletingRef.current) setConfirmOpen(false); }}
      onConfirm={() => void confirmDelete()}
    />
  </>;
}
