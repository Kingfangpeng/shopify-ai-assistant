import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi, setCsrfToken } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const check = useCallback(async () => {
    try {
      const data = await authApi.me()
      setUser(data.user)
    } catch {
      setCsrfToken('')
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    check()
    const unauthorized = () => { setCsrfToken(''); setUser(null) }
    window.addEventListener('auth:unauthorized', unauthorized)
    return () => window.removeEventListener('auth:unauthorized', unauthorized)
  }, [check])

  const login = async (username, password) => {
    const data = await authApi.login(username, password)
    setUser(data.user)
    return data
  }
  const logout = async () => {
    try { await authApi.logout() } finally { setCsrfToken(''); setUser(null) }
  }

  const value = useMemo(() => ({ user, loading, login, logout, check }), [user, loading, check])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
