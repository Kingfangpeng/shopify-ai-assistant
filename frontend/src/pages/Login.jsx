import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, LockKeyhole, ShieldCheck, ShoppingBag } from 'lucide-react'
import { useAuth } from '../auth/AuthContext.jsx'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('king')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/chat" replace />

  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await login(username, password)
      navigate(location.state?.from || '/chat', { replace: true })
    } catch (err) {
      setError(err.message || '登录失败')
    } finally { setBusy(false) }
  }

  return (
    <main className="login-shell">
      <section className="login-story" aria-label="产品介绍">
        <div className="brand-mark"><ShoppingBag size={21} /> MERCHANT DESK</div>
        <div>
          <p className="eyebrow">LOCAL-FIRST COMMERCE INTELLIGENCE</p>
          <h1>把店铺数据，变成<br />下一步行动。</h1>
          <p className="login-copy">只读连接 Shopify GraphQL。聊天、文档与会话保留在本机。</p>
        </div>
        <div className="trust-line"><ShieldCheck size={18} /> 仅监听 127.0.0.1 · 8 小时绝对会话</div>
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="login-icon"><LockKeyhole size={22} /></div>
          <p className="eyebrow">ADMIN ACCESS</p>
          <h2>登录运营台</h2>
          <p className="muted">使用本机管理员账号继续。</p>
          <label>用户名<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label>
          <label>密码<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="primary-button" disabled={busy}>{busy ? '验证中…' : <>进入运营台 <ArrowRight size={16} /></>}</button>
          <p className="login-hint">首次使用：<code>python -m app.cli create-admin --username king</code></p>
        </form>
      </section>
    </main>
  )
}
