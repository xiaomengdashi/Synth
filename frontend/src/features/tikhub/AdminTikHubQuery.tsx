import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ChevronLeft, ChevronRight, Copy, Download, ExternalLink, Search } from 'lucide-react';
import AdminPageHeader from '../tasks/components/AdminPageHeader';
import { buildParameters, dateTime, fieldSchema, requestJson, schemaType } from './client';
import type { Catalog, Endpoint, KeyStatus, QueryParameter, QueryResult } from './types';

function ParameterField({ field, value, onChange }: { field: QueryParameter; value: string; onChange: (value: string) => void }) {
  const schema = fieldSchema(field.schema);
  const type = schemaType(field.schema);
  const id = `param-${field.name}`;
  const common = { id, value, required: field.required, 'aria-describedby': `${id}-help` };
  const hint = field.example ?? field.schema.default;
  const placeholder = hint == null ? (field.required ? '必填' : '留空使用接口默认值') : typeof hint === 'object' ? JSON.stringify(hint) : String(hint);
  return <div className={`form-field ${['object', 'array'].includes(type) ? 'full' : ''}`}>
    <label htmlFor={id}>{field.description?.split('/')[0]?.split('\n')[0]?.slice(0, 70) || field.name}{field.required && <span className="tikhub-required"> *</span>}<code>{field.name}</code></label>
    {schema.enum ? <select {...common} onChange={event => onChange(event.target.value)}><option value="">{field.required ? '请选择' : '使用默认值'}</option>{schema.enum.map(option => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select>
      : type === 'boolean' ? <select {...common} onChange={event => onChange(event.target.value)}><option value="">使用默认值</option><option value="true">是（true）</option><option value="false">否（false）</option></select>
      : ['array', 'object'].includes(type) ? <textarea {...common} rows={5} spellCheck={false} placeholder={placeholder} onChange={event => onChange(event.target.value)} />
      : <input {...common} type={/cookie|token|password/i.test(field.name) ? 'password' : 'text'} autoComplete="off" spellCheck={false}
          inputMode={['integer', 'number'].includes(type) ? 'decimal' : undefined} maxLength={schema.maxLength}
          placeholder={placeholder} onChange={event => onChange(event.target.value)} />}
    <p id={`${id}-help`} className="form-help">{type === 'integer' ? '整数' : type === 'number' ? '数字' : ['array', 'object'].includes(type) ? 'JSON 格式，长 ID 请加引号' : type === 'boolean' ? '布尔值' : '文本'}
      {field.schema.default !== undefined && ` · 默认：${JSON.stringify(field.schema.default)}`}
      {schema.minimum !== undefined && ` · 最小 ${schema.minimum}`}{schema.maximum !== undefined && ` · 最大 ${schema.maximum}`}</p>
  </div>;
}

function DataTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null) return <span className="tikhub-tree-scalar">null</span>;
  if (typeof value !== 'object') {
    const text = String(value);
    return <span className="tikhub-tree-scalar">{text.length > 2000 ? `${text.slice(0, 2000)}…（完整内容见 JSON 导出）` : text}</span>;
  }
  const entries = Object.entries(value);
  if (depth > 8) return <span>层级较深，请查看 JSON。</span>;
  return <div className="tikhub-tree">{!entries.length && <span>{Array.isArray(value) ? '[]' : '{}'}</span>}
    {entries.slice(0, 80).map(([name, child]) => <div key={name}>
      {child !== null && typeof child === 'object' ? <details open={depth < 1}><summary><strong>{name}</strong><small>{Array.isArray(child) ? `${child.length} 项` : `${Object.keys(child).length} 个字段`}</small></summary><DataTree value={child} depth={depth + 1} /></details>
        : <div className="tikhub-tree-row"><strong>{name}</strong><DataTree value={child} depth={depth + 1} /></div>}
    </div>)}{entries.length > 80 && <p className="form-help">当前展示前 80 项，全部 {entries.length} 项可导出查看。</p>}</div>;
}

export default function AdminTikHubQuery() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [platform, setPlatform] = useState('twitter');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Endpoint | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [key, setKey] = useState<KeyStatus | null>(null);
  const [keyError, setKeyError] = useState('');
  const [catalogError, setCatalogError] = useState('');
  const [queryError, setQueryError] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [view, setView] = useState<'tree' | 'json'>('tree');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const queryController = useRef<AbortController | null>(null);
  const queryVersion = useRef(0);

  const selectEndpoint = (endpoint: Endpoint | null) => {
    queryController.current?.abort(); queryVersion.current++;
    setRunning(false); setSelected(endpoint); setValues({}); setResult(null); setQueryError(''); setNotice('');
  };

  useEffect(() => {
    const controller = new AbortController();
    setKeyError('');
    void requestJson<KeyStatus>('/api/v1/tikhub/key', { signal: controller.signal }).then(setKey)
      .catch(e => { if (!controller.signal.aborted) setKeyError(e instanceof Error ? e.message : 'Key 状态读取失败'); });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setCatalogError('');
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ platform, q: search, offset: String(offset), limit: '30' });
      void requestJson<Catalog>(`/api/v1/tikhub/catalog?${params}`, { signal: controller.signal }).then(data => {
        if (controller.signal.aborted) return;
        setCatalog(data); setSelected(data.items[0] || null); setValues({}); setLoading(false);
      }).catch(e => {
        if (!controller.signal.aborted) { setCatalogError(e instanceof Error ? e.message : '目录加载失败'); setLoading(false); }
      });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [platform, search, offset, reload]);

  useEffect(() => () => { queryController.current?.abort(); queryVersion.current++; }, []);

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected || running) return;
    setQueryError(''); setResult(null); setNotice('');
    let parameters;
    try { parameters = buildParameters(selected.parameters, values); }
    catch (e) { setQueryError(e instanceof Error ? e.message : '请检查查询参数'); return; }
    const version = ++queryVersion.current;
    const controller = new AbortController();
    queryController.current = controller;
    setRunning(true);
    try {
      const data = await requestJson<QueryResult>('/api/v1/tikhub/query', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint_id: selected.id, parameters }), signal: controller.signal,
      });
      if (version === queryVersion.current) setResult(data);
    } catch (e) {
      if (!controller.signal.aborted && version === queryVersion.current) setQueryError(e instanceof Error ? e.message : '查询失败');
    } finally { if (version === queryVersion.current) setRunning(false); }
  };

  const resultJson = result ? JSON.stringify(result.data, null, 2) : '';
  const copy = async () => {
    try { await navigator.clipboard.writeText(resultJson); setNotice('查询结果已复制。'); }
    catch { setNotice('复制不可用，请使用 JSON 导出。'); }
  };
  const download = () => {
    const blob = new Blob([resultJson], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `tikhub-${result?.endpoint.path.split('/').pop() || 'result'}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return <div className="tikhub-page">
    <AdminPageHeader eyebrow="TikHub / Explorer" title="多平台数据查询" description="选择平台与接口，填写参数，用已保存的 Key 获取实时数据。"
      actions={<Link to="/admin/settings?tab=tikhub" className="secondary-button"><ArrowLeft size={14} /> Key 与账户</Link>} />
    <nav className="tikhub-tabs" aria-label="TikHub 页面"><Link to="/admin/settings?tab=tikhub">Key 与账户</Link><Link className="active" aria-current="page" to="/admin/tikhub/query">多平台查询</Link></nav>
    {keyError ? <p className="tikhub-message error" role="alert">{keyError} <button className="tiny-button" onClick={() => setReload(reload + 1)}>重试</button></p>
      : key && !key.configured ? <p className="tikhub-message warning">尚未配置 Key。可以浏览目录，<Link to="/admin/settings?tab=tikhub">设置 Key</Link> 后即可查询。</p>
      : key?.configured && <p className="tikhub-key-status"><span className="config-status ready">Key 已配置</span><code>{key.masked_key}</code><span>每次查询可能计费，请按需执行。</span></p>}
    <div className="tikhub-explorer">
      <section className="settings-panel tikhub-catalog" aria-busy={loading}>
        <h2><Search size={16} /> 查询目录</h2>
        <div className="form-field"><label htmlFor="query-platform">平台</label><select id="query-platform" value={platform} onChange={e => { selectEndpoint(null); setPlatform(e.target.value); setOffset(0); }}>
          <option value="">全部平台</option>{catalog ? catalog.platforms.map(p => <option key={p.id} value={p.id}>{p.name}（{p.count}）</option>) : <option value="twitter">X / Twitter</option>}
        </select></div>
        <div className="form-field"><label htmlFor="query-search">搜索接口</label><input id="query-search" type="search" maxLength={200} value={search} onChange={e => { selectEndpoint(null); setSearch(e.target.value); setOffset(0); }} placeholder="内容、用户、评论、搜索…" /></div>
        {catalogError ? <p className="tikhub-message error" role="alert">{catalogError}<button className="tiny-button" onClick={() => setReload(reload + 1)}>重新加载</button></p>
          : loading ? <p className="tikhub-empty" role="status">正在加载目录…</p>
          : <><p className="form-help">共 {catalog?.total || 0} 个接口 · 目录 {catalog?.generated_at}</p>
            <div className="tikhub-endpoint-list" aria-label="可用查询接口">
              {catalog?.items.map(endpoint => <button type="button" key={endpoint.id} aria-pressed={selected?.id === endpoint.id}
                className={selected?.id === endpoint.id ? 'selected' : ''} onClick={() => selectEndpoint(endpoint)}>
                <strong>{endpoint.title}</strong><span>{endpoint.group}</span><code>{endpoint.path.split('/').pop()}</code>
              </button>)}
              {!catalog?.items.length && <p className="tikhub-empty">没有匹配接口，请换个关键词或平台。</p>}
            </div>
            <div className="tikhub-pagination"><button type="button" className="tiny-button" aria-label="上一页接口" disabled={!offset} onClick={() => { selectEndpoint(null); setOffset(Math.max(0, offset - 30)); }}><ChevronLeft size={14} /></button>
              <span>{catalog?.total ? `${offset + 1}–${Math.min(offset + 30, catalog.total)} / ${catalog.total}` : '0 / 0'}</span>
              <button type="button" className="tiny-button" aria-label="下一页接口" disabled={offset + 30 >= (catalog?.total || 0)} onClick={() => { selectEndpoint(null); setOffset(offset + 30); }}><ChevronRight size={14} /></button></div>
          </>}
      </section>
      <div className="tikhub-query-main">
        <section className="settings-panel settings-form-panel">
          {selected && !loading ? <>
            <div className="tikhub-section-heading"><h2>{selected.title}</h2><a href={selected.docs_url} target="_blank" rel="noreferrer" className="text-link">官方说明 <ExternalLink size={13} /></a></div>
            <p className="tikhub-endpoint-path"><span>{selected.method}</span> {selected.path}</p>
            {selected.description && <details className="tikhub-disclosure"><summary>用途与参数说明</summary><pre>{selected.description}</pre></details>}
            <form onSubmit={run}>
              <fieldset disabled={running} className="tikhub-parameter-fields"><div className="form-grid">
                {selected.parameters.map(field => <ParameterField key={field.name} field={field} value={values[field.name] || ''} onChange={value => { setValues({ ...values, [field.name]: value }); setResult(null); setNotice(''); }} />)}
              </div></fieldset>
              {!selected.parameters.length && <p className="tikhub-empty">此接口无需填写参数。</p>}
              {queryError && <p className="tikhub-message error" role="alert">{queryError}</p>}
              <div className="modal-footer"><p className="form-help">以此 Key 的权限和额度为准；部分接口还需平台 Cookie 等参数。</p><button type="submit" className="primary-button" disabled={running || !key?.configured || !!keyError}>{running ? '查询中…' : '执行查询'}</button></div>
            </form>
          </> : <p className="tikhub-empty">从左侧选择一个查询接口。</p>}
        </section>
        <section className="settings-panel tikhub-results" aria-busy={running}>
          <div className="tikhub-section-heading"><h2>查询结果</h2>{result && <div className="tikhub-result-actions"><button type="button" className="tiny-button" onClick={() => void copy()}><Copy size={13} /> 复制</button><button type="button" className="tiny-button" onClick={download}><Download size={13} /> 导出 JSON</button></div>}</div>
          {running ? <p className="tikhub-empty" role="status">正在向 TikHub 查询，请稍候…</p> : result ? <>
            <p className="form-help">{result.endpoint.title} · {dateTime(result.queried_at)}</p>
            <div className="tikhub-result-actions"><button type="button" className="tiny-button" aria-pressed={view === 'tree'} onClick={() => setView('tree')}>字段视图</button><button type="button" className="tiny-button" aria-pressed={view === 'json'} onClick={() => setView('json')}>JSON 视图</button></div>
            {view === 'tree' ? <DataTree value={result.data} /> : <pre className="tikhub-json">{resultJson.slice(0, 200_000)}{resultJson.length > 200_000 ? '\n…预览已截断，请导出完整 JSON。' : ''}</pre>}
            {notice && <p className="tikhub-message" role="status">{notice}</p>}
          </> : <p className="tikhub-empty">执行查询后，数据会显示在这里。支持展开字段、复制和导出。</p>}
        </section>
      </div>
    </div>
  </div>;
}
