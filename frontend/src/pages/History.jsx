import { useState } from 'react'
import { MessageSquare, ChevronDown, ChevronUp, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

function groupByDate(sessions) {
  const now = Date.now()
  const DAY = 86400000
  const groups = { today: [], yesterday: [], earlier: [] }

  Object.values(sessions)
    .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
    .forEach(s => {
      const age = now - (s.createdAt || 0)
      if (age < DAY) groups.today.push(s)
      else if (age < DAY * 2) groups.yesterday.push(s)
      else groups.earlier.push(s)
    })

  return groups
}

function SessionCard({ session, onGoto }) {
  const [expanded, setExpanded] = useState(false)
  const userMsgs = (session.messages || []).filter(m => m.role === 'user')
  const date = session.createdAt
    ? new Date(session.createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : ''

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="w-8 h-8 rounded-full bg-brand-50 flex items-center justify-center shrink-0">
          <MessageSquare size={15} className="text-brand-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800 truncate">{session.title || '新对话'}</p>
          <p className="text-xs text-slate-400 mt-0.5">{date} · {userMsgs.length} 条提问</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={e => { e.stopPropagation(); onGoto(session.id) }}
            className="text-xs text-brand-500 hover:text-brand-600 flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-brand-50 transition-colors"
          >
            继续 <ArrowRight size={12} />
          </button>
          {expanded ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-slate-100 divide-y divide-slate-50">
          {(session.messages || []).map((msg, i) => (
            <div key={i} className={`px-4 py-2.5 ${msg.role === 'user' ? 'bg-slate-50' : 'bg-white'}`}>
              <span className="text-xs font-medium text-slate-400 mr-2">
                {msg.role === 'user' ? '你' : 'AI'}
              </span>
              <span className="text-sm text-slate-700 whitespace-pre-wrap">
                {msg.content?.slice(0, 300)}{msg.content?.length > 300 ? '…' : ''}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function History({ sessions = {}, onSelect }) {
  const navigate = useNavigate()
  const groups = groupByDate(sessions)
  const total = Object.keys(sessions).length

  const handleGoto = (id) => {
    onSelect?.(id)
    navigate('/chat')
  }

  return (
    <div className="flex flex-col h-screen max-h-screen">
      <div className="flex items-center px-6 py-3.5 bg-white border-b border-slate-200 shrink-0">
        <h1 className="text-[15px] font-semibold text-slate-800">对话历史</h1>
        <span className="ml-2 text-xs text-slate-400">{total} 个会话</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 space-y-6">
        {total === 0 && (
          <div className="flex flex-col items-center justify-center h-64 text-slate-400">
            <MessageSquare size={36} className="mb-3 opacity-40" />
            <p className="text-sm">暂无对话历史</p>
          </div>
        )}

        {groups.today.length > 0 && (
          <section>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">今天</h2>
            <div className="space-y-2">
              {groups.today.map(s => <SessionCard key={s.id} session={s} onGoto={handleGoto} />)}
            </div>
          </section>
        )}

        {groups.yesterday.length > 0 && (
          <section>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">昨天</h2>
            <div className="space-y-2">
              {groups.yesterday.map(s => <SessionCard key={s.id} session={s} onGoto={handleGoto} />)}
            </div>
          </section>
        )}

        {groups.earlier.length > 0 && (
          <section>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">更早</h2>
            <div className="space-y-2">
              {groups.earlier.map(s => <SessionCard key={s.id} session={s} onGoto={handleGoto} />)}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
