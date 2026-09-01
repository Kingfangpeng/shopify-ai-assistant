import { ArrowUpRight, Clock3, MessageSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export default function History({ sessions, onSelect }) {
  const navigate = useNavigate()
  const open = id => { onSelect(id); navigate('/chat') }
  return <div className="page history-page">
    <header className="page-header"><div><p className="eyebrow">SERVER-SIDE HISTORY</p><h1>对话历史</h1><p>会话存储在本机 SQLite，不再依赖浏览器缓存。</p></div><span className="metric-chip">{sessions.length} 个会话</span></header>
    {!sessions.length ? <div className="panel empty-panel large"><MessageSquare size={34} /><p>还没有历史对话</p></div> : <section className="history-list">
      {sessions.map(item => <button className="history-row" key={item.id} onClick={() => open(item.id)}>
        <span className="history-icon"><MessageSquare size={17} /></span><span className="history-copy"><b>{item.title}</b><small><Clock3 size={12} />{new Date(item.updated_at).toLocaleString('zh-CN')}</small></span><ArrowUpRight size={17} />
      </button>)}
    </section>}
  </div>
}
