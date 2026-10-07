import { useEffect, useState } from 'react';
import { Download, Loader2, Plus, Tags, Trash2 } from 'lucide-react';
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
  // 并发导出互不干扰:按分类名逐行跟踪 spinner(同时点两个分类时各自独立收尾)
  const [exporting, setExporting] = useState<Set<string>>(new Set());

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

  // 批量导出需携带 X-Admin-Token,走 adminFetch 取 blob 后本地触发下载;
  // param 支持与展示名分离:「未分类」伪分类请求参数是 __none__
  const exportCategory = async (name: string, param = name) => {
    setExporting((prev) => new Set(prev).add(name));
    try {
      const res = await adminFetch(`/api/v1/articles/export-batch?category=${encodeURIComponent(param)}`);
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || '导出失败');
      }
      const blob = await res.blob();
      // 后端 Content-Disposition 用 filename*=UTF-8'' 编码中文 zip 名,前端解码还原
      const encoded = (res.headers.get('Content-Disposition') || '').match(/filename\*=UTF-8''([^;\s]+)/);
      const filename = encoded ? decodeURIComponent(encoded[1]) : `notes-${name}.zip`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
      pushToast({ title: '笔记已导出', tone: 'success' });
    } catch (error) {
      pushToast({ title: error instanceof Error && error.message ? error.message : '导出笔记失败，请稍后重试', tone: 'error' });
    } finally {
      setExporting((prev) => {
        const next = new Set(prev);
        next.delete(name);
        return next;
      });
    }
  };

  return (
    <div>
      <AdminPageHeader
        summary={<span>共 {names.length} 个分类 · 到「文章管理」为每篇文章选择分类</span>}
      />
      <section className="ac-card">
        <div className="ac-card-head">
          <h2 className="ac-card-title"><Tags size={15} />文章分类</h2>
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
                    <button
                      type="button"
                      className="ac-btn secondary sm"
                      onClick={() => void exportCategory(name)}
                      disabled={exporting.has(name) || saving}
                    >
                      {exporting.has(name) ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}导出笔记
                    </button>
                    <button type="button" className="ac-btn danger-ghost sm" onClick={() => setPendingDelete(name)} disabled={saving}>
                      <Trash2 size={13} />删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {/* 未分类不是分类实体(不在 names 里),但导出必须可达:懒分类/新库时它是唯一入口 */}
          <div className="category-manage-row" style={{ marginTop: 14 }}>
            <span>未分类 <span className="ac-card-caption">未选分类的文章</span></span>
            <div className="ac-row-actions">
              <button
                type="button"
                className="ac-btn secondary sm"
                onClick={() => void exportCategory('未分类', '__none__')}
                disabled={exporting.has('未分类') || saving}
              >
                {exporting.has('未分类') ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}导出笔记
              </button>
            </div>
          </div>
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
