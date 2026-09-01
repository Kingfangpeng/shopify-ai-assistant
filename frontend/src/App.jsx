import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { chatApi, fetchHealth } from './api/client.js'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import Sidebar from './components/Sidebar.jsx'
import Chat from './pages/Chat.jsx'
import History from './pages/History.jsx'
import Knowledge from './pages/Knowledge.jsx'
import Login from './pages/Login.jsx'
import Settings from './pages/Settings.jsx'

const LEGACY_KEY = 'shopify_ai_sessions'

function Workspace() {
  const { user, logout } = useAuth()
  const [sessions, setSessions] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [activeSession, setActiveSession] = useState(null)
  const [systemOk, setSystemOk] = useState(null)
  const [loading, setLoading] = useState(true)

  const refreshSessions = useCallback(async () => {
    const data = await chatApi.list()
    setSessions(data.items || [])
    return data.items || []
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) || '{}')
        if (Object.keys(legacy).length) {
          await chatApi.importLegacy(Object.values(legacy))
          localStorage.removeItem(LEGACY_KEY)
          localStorage.removeItem('shopify_ai_active_session')
        }
        let items = await refreshSessions()
        if (!items.length) {
          const created = await chatApi.create()
          items = [created]; setSessions(items)
        }
        if (!cancelled) setActiveId(items[0]?.id || null)
      } finally { if (!cancelled) setLoading(false) }
    }
    load()
    fetchHealth().then(() => setSystemOk(true)).catch(() => setSystemOk(false))
    return () => { cancelled = true }
  }, [refreshSessions])

  useEffect(() => {
    if (!activeId) return setActiveSession(null)
    chatApi.get(activeId).then(setActiveSession).catch(() => setActiveSession(null))
  }, [activeId])

  const createSession = async () => {
    const created = await chatApi.create()
    setSessions(items => [created, ...items]); setActiveId(created.id); setActiveSession(created)
  }
  const deleteSession = async id => {
    if (!window.confirm('删除这个对话及其全部消息？此操作无法恢复。')) return
    await chatApi.remove(id)
    const remaining = sessions.filter(item => item.id !== id)
    setSessions(remaining)
    if (activeId === id) setActiveId(remaining[0]?.id || null)
  }
  const refreshActive = async () => {
    if (!activeId) return
    const detail = await chatApi.get(activeId)
    setActiveSession(detail); await refreshSessions()
  }

  return (
    <div className="app-shell">
      <Sidebar systemOk={systemOk} sessions={sessions} activeId={activeId} onSelect={setActiveId}
        onCreate={createSession} onDelete={deleteSession} user={user} onLogout={logout} />
      <main className="app-main">
        {loading ? <div className="screen-loader">正在加载运营台…</div> : (
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<Chat session={activeSession} onComplete={refreshActive} />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/history" element={<History sessions={sessions} onSelect={setActiveId} />} />
            <Route path="/settings" element={<Settings user={user} systemOk={systemOk} />} />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        )}
      </main>
    </div>
  )
}

function AppRoutes() {
  return <Routes>
    <Route path="/login" element={<Login />} />
    <Route path="/*" element={<ProtectedRoute><Workspace /></ProtectedRoute>} />
  </Routes>
}

export default function App() {
  return <BrowserRouter><AuthProvider><AppRoutes /></AuthProvider></BrowserRouter>
}
