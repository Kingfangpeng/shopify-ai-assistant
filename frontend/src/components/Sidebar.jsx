import { NavLink, useNavigate } from 'react-router-dom'
import { MessageSquare, BookOpen, Settings, ShoppingBag, Menu, X, Plus, Trash2, Clock } from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { to: '/knowledge', icon: BookOpen,       label: '知识库' },
  { to: '/history',   icon: Clock,           label: '历史记录' },
  { to: '/settings',  icon: Settings,        label: '设置' },
]

function groupSessions(sessions) {
  const now = Date.now()
  const oneDayMs = 86400000
  const today = [], yesterday = [], earlier = []
  const sorted = Object.values(sessions).sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
  for (const s of sorted) {
    const diff = now - (s.createdAt || 0)
    if (diff < oneDayMs)         today.push(s)
    else if (diff < oneDayMs * 2) yesterday.push(s)
    else                          earlier.push(s)
  }
  return { today, yesterday, earlier }
}

export default function Sidebar({ systemOk, sessions = {}, activeId, onSelect, onCreate, onDelete }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [hoverId, setHoverId]       = useState(null)
  const navigate = useNavigate()
  const groups = groupSessions(sessions)

  const handleSelect = (id) => {
    onSelect(id)
    navigate('/chat')
    setMobileOpen(false)
  }

  const handleCreate = () => {
    onCreate()
    navigate('/chat')
    setMobileOpen(false)
  }

  const SessionItem = ({ s }) => (
    <div
      key={s.id}
      className={`group relative flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer text-xs transition-colors ${
        s.id === activeId
          ? 'bg-brand-50 text-brand-700'
          : 'text-slate-600 hover:bg-slate-100'
      }`}
      onMouseEnter={() => setHoverId(s.id)}
      onMouseLeave={() => setHoverId(null)}
      onClick={() => handleSelect(s.id)}
    >
      <MessageSquare size={13} className="shrink-0 opacity-60" />
      <span className="flex-1 truncate leading-relaxed">{s.title || '新对话'}</span>
      {hoverId === s.id && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(s.id) }}
          className="shrink-0 p-0.5 rounded hover:text-red-500 transition-colors"
        >
          <Trash2 size={12} />
        </button>
      )}
    </div>
  )

  const SessionGroup = ({ label, items }) => {
    if (!items.length) return null
    return (
      <div className="mb-3">
        <p className="px-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">{label}</p>
        {items.map(s => <SessionItem key={s.id} s={s} />)}
      </div>
    )
  }

  const NavContent = () => (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-slate-100 shrink-0">
        <div className="w-7 h-7 bg-brand-500 rounded-lg flex items-center justify-center">
          <ShoppingBag size={15} className="text-white" />
        </div>
        <span className="font-semibold text-slate-800 text-[14px]">Shopify AI</span>
      </div>

      {/* 新建对话按钮 */}
      <div className="px-3 py-3 shrink-0">
        <button
          onClick={handleCreate}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-brand-500 text-white text-xs font-medium hover:bg-brand-600 transition-colors"
        >
          <Plus size={14} />
          新建对话
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 min-h-0">
        {Object.keys(sessions).length === 0 ? (
          <p className="text-xs text-slate-400 text-center py-4">暂无对话记录</p>
        ) : (
          <>
            <SessionGroup label="今天" items={groups.today} />
            <SessionGroup label="昨天" items={groups.yesterday} />
            <SessionGroup label="更早" items={groups.earlier} />
          </>
        )}
      </div>

      {/* 底部导航 */}
      <div className="border-t border-slate-100 px-2 py-2 shrink-0">
        <nav className="space-y-0.5">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-2 py-2 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-50 text-brand-600'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* 状态 */}
        <div className="flex items-center gap-2 text-[10px] text-slate-400 mt-2 px-2">
          <span className={`w-1.5 h-1.5 rounded-full ${systemOk ? 'bg-emerald-400' : 'bg-red-400'}`} />
          {systemOk === null ? '检测中...' : systemOk ? '系统正常' : '系统异常'}
        </div>
      </div>
    </div>
  )

  return (
    <>
      {/* 桌面侧边栏 */}
      <aside className="hidden md:flex flex-col w-52 bg-white border-r border-slate-200 shrink-0 h-screen sticky top-0">
        <NavContent />
      </aside>

      {/* 移动端顶部栏 */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 bg-white border-b border-slate-200 flex items-center px-4 h-14">
        <button onClick={() => setMobileOpen(true)} className="p-1.5 rounded-lg hover:bg-slate-100">
          <Menu size={20} />
        </button>
        <span className="ml-3 font-semibold text-slate-800">Shopify AI</span>
      </div>

      {/* 移动端抽屉 */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div className="w-56 bg-white h-full shadow-xl">
            <div className="flex justify-end p-3">
              <button onClick={() => setMobileOpen(false)} className="p-1.5 rounded-lg hover:bg-slate-100">
                <X size={20} />
              </button>
            </div>
            <NavContent />
          </div>
          <div className="flex-1 bg-black/40" onClick={() => setMobileOpen(false)} />
        </div>
      )}
    </>
  )
}
