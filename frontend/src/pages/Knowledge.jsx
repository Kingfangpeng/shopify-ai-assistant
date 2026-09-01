import { useEffect, useRef, useState } from 'react'
import { ArchiveRestore, FileText, Layers3, RefreshCw, Trash2, UploadCloud, X } from 'lucide-react'
import { knowledgeApi } from '../api/client.js'

export default function Knowledge() {
  const [tab, setTab] = useState('active')
  const [documents, setDocuments] = useState([])
  const [selected, setSelected] = useState(null)
  const [chunks, setChunks] = useState([])
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const inputRef = useRef(null)

  const load = async nextTab => {
    const mode = nextTab || tab
    setBusy('loading')
    try { const data = await knowledgeApi.list(mode); setDocuments(data.items || []) }
    catch (error) { setNotice({ type: 'error', text: error.message }) }
    finally { setBusy('') }
  }
  useEffect(() => { setSelected(null); setChunks([]); load(tab) }, [tab]) // eslint-disable-line

  const upload = async event => {
    const file = event.target.files?.[0]; if (!file) return
    setBusy('uploading'); setNotice({ type: 'info', text: '正在校验文件并生成向量…' })
    try { await knowledgeApi.upload(file); setNotice({ type: 'success', text: `${file.name} 已安全索引` }); await load('active') }
    catch (error) { setNotice({ type: 'error', text: error.message }) }
    finally { setBusy(''); event.target.value = '' }
  }
  const showChunks = async doc => {
    setSelected(doc); setBusy('chunks')
    try { const data = await knowledgeApi.chunks(doc.id); setChunks(data.items || []) }
    catch (error) { setNotice({ type: 'error', text: error.message }) }
    finally { setBusy('') }
  }
  const remove = async doc => {
    if (!window.confirm(`将“${doc.name}”移入回收站？7 天内可以恢复。`)) return
    try { await knowledgeApi.remove(doc.id); setNotice({ type: 'success', text: '文档已移入回收站' }); await load() }
    catch (error) { setNotice({ type: 'error', text: error.message }) }
  }
  const restore = async doc => {
    setBusy(doc.id)
    try { await knowledgeApi.restore(doc.id); setNotice({ type: 'success', text: '文档已恢复并重新索引' }); await load() }
    catch (error) { setNotice({ type: 'error', text: error.message }) }
    finally { setBusy('') }
  }
  const rebuild = async () => {
    if (!window.confirm('重新索引上传目录中的全部有效文档？旧向量会保留到新向量写入成功。')) return
    setBusy('rebuild'); setNotice({ type: 'info', text: '正在逐份重建索引…' })
    try { const data = await knowledgeApi.rebuild(); setNotice({ type: data.failed?.length ? 'error' : 'success', text: `完成 ${data.rebuilt} 份，失败 ${data.failed?.length || 0} 份` }); await load() }
    catch (error) { setNotice({ type: 'error', text: error.message }) }
    finally { setBusy('') }
  }

  return <div className="page knowledge-page">
    <header className="page-header"><div><p className="eyebrow">TRUSTED OPERATIONS</p><h1>知识库</h1><p>文件与向量由服务端文档 ID 管理，不暴露本机路径。</p></div><div className="header-actions">
      <button className="secondary-button" onClick={rebuild} disabled={!!busy}><RefreshCw size={15} className={busy === 'rebuild' ? 'spin' : ''} />重建</button>
      <button className="primary-button" onClick={() => inputRef.current?.click()} disabled={!!busy}><UploadCloud size={16} />上传文档</button>
      <input ref={inputRef} type="file" accept=".txt,.md,text/plain,text/markdown" hidden onChange={upload} />
    </div></header>
    {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.text}</span><button onClick={() => setNotice(null)}><X size={15} /></button></div>}
    <div className="tab-bar"><button className={tab === 'active' ? 'active' : ''} onClick={() => setTab('active')}>有效文档</button><button className={tab === 'trashed' ? 'active' : ''} onClick={() => setTab('trashed')}>回收站</button></div>
    <div className="knowledge-grid">
      <section className="panel document-panel"><div className="panel-heading"><span>{tab === 'active' ? '已索引文件' : '7 天回收站'}</span><small>{documents.length} 项</small></div>
        {busy === 'loading' ? <SkeletonList /> : !documents.length ? <div className="empty-panel"><FileText size={30} /><p>{tab === 'active' ? '还没有文档' : '回收站为空'}</p></div> : documents.map(doc => <div className={`document-row ${selected?.id === doc.id ? 'selected' : ''}`} key={doc.id}>
          <button className="document-main" onClick={() => tab === 'active' && showChunks(doc)}><span className="file-icon"><FileText size={17} /></span><span><b>{doc.name}</b><small>{doc.chunk_count} 个分片 · v{doc.version} · {formatBytes(doc.size_bytes)}</small></span></button>
          {tab === 'active' ? <button className="icon-button danger" onClick={() => remove(doc)} aria-label="移入回收站"><Trash2 size={15} /></button> : <button className="icon-button" disabled={busy === doc.id} onClick={() => restore(doc)} aria-label="恢复"><ArchiveRestore size={16} /></button>}
        </div>)}
      </section>
      <section className="panel chunk-panel"><div className="panel-heading"><span>{selected ? selected.name : '文档分片'}</span><small>{chunks.length ? `${chunks.length} 条` : ''}</small></div>
        {!selected ? <div className="empty-panel"><Layers3 size={30} /><p>选择一份文档查看实际入库内容</p></div> : busy === 'chunks' ? <SkeletonList /> : chunks.map(chunk => <article className="chunk-card" key={chunk.id}><div><Layers3 size={15} /><b>{[chunk.h1, chunk.h2].filter(Boolean).join(' / ') || '文本片段'}</b><small>{chunk.char_count} 字符</small></div><p>{chunk.content}</p></article>)}
      </section>
    </div>
  </div>
}

function SkeletonList() { return <div className="skeleton-list">{[1, 2, 3].map(item => <span key={item} />)}</div> }
function formatBytes(value) { return value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB` }
