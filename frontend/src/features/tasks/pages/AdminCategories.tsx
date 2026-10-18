import { useEffect, useState } from 'react';
import { Plus, Tags, Trash2 } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../components/AdminPageHeader';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { adminFetch } from '../../../utils/adminAuth';

/** 文章分类管理:维护前台「分类」菜单使用的分类列表。 */
export default function AdminCategories() {
  const pushToast = useAppStore((state) => state.pushToast);
  const [names, setNames] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetch('/api/v1/categories')
      .then((res) => (res.ok ? res.json() : { names: [] }))
      .then((data: { names?: string[] }) => setNames(data.names ?? []))
      .catch(() => setNames([]))
      .finally(() => setLoading(false));
  }, []);

  const persist = async (next: string[]) => {
    setSaving(true);
    try {
      const res = await adminFetch('/api/v1/categories', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names: next }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error('save failed');
      setNames(data.names ?? next);
      pushToast({ title: '分类已保存', tone: 'success' });
    } catch {
      pushToast({ title: '分类保存失败，请稍后重试', tone: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const add = () => {
    const value = input.trim();
    if (!value) return;
    if (names.includes(value)) {
      pushToast({ title: '这个分类已存在', tone: 'error' });
      return;
    }
    setInput('');
    void persist([...names, value]);
  };

  return (
    <div>
      <AdminPageHeader
        summary={<span>共 {names.length} 个分类 · 到「文章管理」为每篇文章选择分类</span>}
      />
      <section className="ac-card">
        <div className="ac-card-head">
          <h2 className="ac-card-title"><Tags size={15} />分类列表</h2>
          <span className="ac-card-caption">{names.length} 个分类</span>
        </div>
        <div className="ac-card-body">
          <div className="category-add-row">
            <input
              className="ac-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') add(); }}
              placeholder="新分类名称"
              disabled={saving}
              aria-label="新分类名称"
            />
            <button type="button" className="ac-btn primary" onClick={add} disabled={saving || !input.trim()}>
              <Plus size={13} />新增分类
            </button>
          </div>
          {loading ? (
            <div className="ac-empty">加载中…</div>
          ) : names.length === 0 ? (
            <div className="ac-empty">还没有分类，先添加一个。</div>
          ) : (
            <div className="ac-stack">
              {names.map((name) => (
                <div key={name} className="category-manage-row">
                  <span>{name}</span>
                  <div className="ac-row-actions">
                    <button type="button" className="ac-btn danger-ghost sm" onClick={() => setPendingDelete(name)} disabled={saving}>
                      <Trash2 size={13} />删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="ac-help">删除分类不会删除文章；已选该分类的文章会自动变为「未分类」。</p>
        </div>
      </section>
      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这个分类？"
        description={pendingDelete ? `已选「${pendingDelete}」分类的文章会自动变为「未分类」，文章本身不受影响。` : undefined}
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (!pendingDelete) return;
          const name = pendingDelete;
          setDeleting(true);
          void persist(names.filter((item) => item !== name)).then(() => {
            setDeleting(false);
            setPendingDelete(null);
          });
        }}
      />
    </div>
  );
}
