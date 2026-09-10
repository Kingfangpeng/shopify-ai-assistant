import { CheckCircle2, Database, ExternalLink } from 'lucide-react'

export default function CitationList({ citations = [] }) {
  if (!citations.length) return null
  return <details className="citation-list">
    <summary><span><Database size={15} /><b>知识库引用</b><small>{citations.length} 个证据片段</small></span><span className="trace-expand">查看来源</span></summary>
    <div className="citation-grid">
      {citations.map((citation, index) => {
        const query = new URLSearchParams({ document: citation.document_id || '', chunk: citation.chunk_id || '' })
        return <article className="citation-card" key={citation.chunk_id || index}>
          <div className="citation-heading">
            <span>{citation.cited && <CheckCircle2 size={14} />}{citation.file_name || '未知来源'}</span>
            <a href={`/knowledge?${query.toString()}`} aria-label={`查看引用 ${citation.file_name || index + 1}`}><ExternalLink size={14} /></a>
          </div>
          <b>{citation.title || `片段 ${citation.rank || index + 1}`}</b>
          <small>v{citation.version ?? '?'} · {citation.chunk_id || '未知 chunk'}{citation.score !== null && citation.score !== undefined ? ` · score ${Number(citation.score).toFixed(3)}` : ''}</small>
          {citation.snippet && <p>{citation.snippet}</p>}
        </article>
      })}
    </div>
  </details>
}
