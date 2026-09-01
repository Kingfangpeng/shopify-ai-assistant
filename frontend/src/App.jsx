import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Chat from './pages/Chat.jsx'
import Knowledge from './pages/Knowledge.jsx'
import Settings from './pages/Settings.jsx'
import History from './pages/History.jsx'
import { fetchHealth } from './api/client.js'

// ── 会话持久化工具 ───────────────────────────────────────
const STORAGE_KEY = 'shopify_ai_sessions'
const ACTIVE_KEY  = 'shopify_ai_active_session'

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
}

function saveSessions(sessions) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions)) } catch {}
}

function genId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2)
}

function newSession(id) {
  return {
    id,
    title: '新对话',
    createdAt: Date.now(),
    messages: [
      {
        role: 'assistant',
        content: '你好！我是 Shopify AI 助手。你可以问我关于产品卖点、广告文案、客服回复、运营策略等问题，我会结合你的知识库来回答。',
      }
    ],
  }
}

export default function App() {
  const [systemOk, setSystemOk]     = useState(null)
  const [sessions, setSessions]     = useState(() => loadSessions())
  const [activeId, setActiveId]     = useState(() => {
    const saved = localStorage.getItem(ACTIVE_KEY)
    return saved || null
  })

  // 确保始终有一个激活的会话
  useEffect(() => {
    const ids = Object.keys(sessions)
    if (!activeId || !sessions[activeId]) {
      if (ids.length > 0) {
        const latest = ids.sort((a, b) => (sessions[b]?.createdAt || 0) - (sessions[a]?.createdAt || 0))[0]
        setActiveId(latest)
      } else {
        // 没有任何会话，新建一个
        const id = genId()
        const s = newSession(id)
        setSessions({ [id]: s })
        setActiveId(id)
      }
    }
  }, []) // eslint-disable-line

  // 持久化 sessions
  useEffect(() => {
    saveSessions(sessions)
  }, [sessions])

  // 持久化 activeId
  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId)
  }, [activeId])

  // 健康检查
  useEffect(() => {
    fetchHealth()
      .then(data => setSystemOk(data?.data?.status === 'healthy'))
      .catch(() => setSystemOk(false))
  }, [])

  // 新建会话
  const createSession = useCallback(() => {
    const id = genId()
    const s = newSession(id)
    setSessions(prev => ({ ...prev, [id]: s }))
    setActiveId(id)
  }, [])

  // 删除会话
  const deleteSession = useCallback((id) => {
    setSessions(prev => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    setActiveId(prev => {
      if (prev !== id) return prev
      const remaining = Object.keys(sessions).filter(k => k !== id)
      return remaining.length > 0 ? remaining[0] : null
    })
  }, [sessions])

  // 更新会话消息（由 Chat 页面调用）
  const updateSessionMessages = useCallback((sessionId, messages) => {
    setSessions(prev => {
      const s = prev[sessionId]
      if (!s) return prev
      // 自动更新标题（取第一条用户消息前20字）
      const firstUser = messages.find(m => m.role === 'user')
      const title = firstUser
        ? firstUser.content.slice(0, 20) + (firstUser.content.length > 20 ? '…' : '')
        : s.title
      return { ...prev, [sessionId]: { ...s, messages, title } }
    })
  }, [])

  const activeSession = activeId ? sessions[activeId] : null

  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-slate-50">
        <Sidebar
          systemOk={systemOk}
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onCreate={createSession}
          onDelete={deleteSession}
        />

        <div className="flex-1 flex flex-col md:pt-0 pt-14 min-w-0">
          <main className="flex-1 overflow-auto">
            <Routes>
              <Route path="/" element={<Navigate to="/chat" replace />} />
              <Route path="/chat" element={
                activeSession
                  ? <Chat
                      key={activeId}
                      session={activeSession}
                      onUpdate={(msgs) => updateSessionMessages(activeId, msgs)}
                    />
                  : <div className="flex items-center justify-center h-full text-slate-400">
                      请先新建一个对话
                    </div>
              } />
              <Route path="/knowledge" element={<Knowledge />} />
              <Route path="/settings" element={<Settings systemOk={systemOk} />} />
              <Route path="/history" element={<History sessions={sessions} onSelect={(id) => { setActiveId(id); }} />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
