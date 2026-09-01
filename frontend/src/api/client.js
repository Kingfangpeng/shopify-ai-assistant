const BASE = ''
let csrfToken = ''

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message)
    this.status = status
    this.code = code
  }
}

export function setCsrfToken(value) {
  csrfToken = value || ''
}

async function parseResponse(response) {
  if (response.status === 204) return null
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const info = payload?.error || {}
    throw new ApiError(info.message || `请求失败（${response.status}）`, response.status, info.code)
  }
  return payload
}

async function refreshCsrf() {
  const response = await fetch(`${BASE}/api/auth/me`, { credentials: 'include' })
  const payload = await parseResponse(response)
  setCsrfToken(payload.csrf_token)
  return payload
}

export async function apiFetch(path, options = {}, retried = false) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers || {})
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(`${BASE}${path}`, { ...options, method, headers, credentials: 'include' })
  if (response.status === 401) window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  if (response.status === 403 && !retried) {
    const body = await response.clone().json().catch(() => ({}))
    if (body?.error?.code === 'csrf_rejected') {
      await refreshCsrf()
      return apiFetch(path, options, true)
    }
  }
  return parseResponse(response)
}

export const authApi = {
  me: refreshCsrf,
  async login(username, password) {
    const response = await fetch(`${BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
    const payload = await parseResponse(response)
    setCsrfToken(payload.csrf_token)
    return payload
  },
  logout: () => apiFetch('/api/auth/logout', { method: 'POST' }),
}

export const fetchHealth = () => apiFetch('/health')
export const fetchConfig = () => apiFetch('/api/config')
export const fetchShopifyStatus = () => apiFetch('/api/shopify/status')

export const chatApi = {
  list: () => apiFetch('/api/chat/sessions'),
  get: (id) => apiFetch(`/api/chat/sessions/${encodeURIComponent(id)}`),
  create: (title = '新对话') => apiFetch('/api/chat/sessions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }),
  }),
  remove: (id) => apiFetch(`/api/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  importLegacy: (sessions) => apiFetch('/api/chat/sessions/import', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessions }),
  }),
}

export function streamChat(sessionId, question, handlers = {}) {
  const controller = new AbortController()
  const run = async (retried = false) => {
    const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }
    const response = await fetch(`${BASE}/api/chat_stream`, {
      method: 'POST', headers, credentials: 'include',
      body: JSON.stringify({ session_id: sessionId, question }), signal: controller.signal,
    })
    if (response.status === 401) window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    if (response.status === 403 && !retried) {
      const body = await response.clone().json().catch(() => ({}))
      if (body?.error?.code === 'csrf_rejected') {
        await refreshCsrf()
        if (!controller.signal.aborted) return run(true)
      }
    }
    if (!response.ok) return parseResponse(response)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() || ''
      for (const event of events) {
        const line = event.split(/\r?\n/).find(item => item.startsWith('data:'))
        if (!line) continue
        const data = JSON.parse(line.slice(5).trim())
        if (data.type === 'status') handlers.onStatus?.(data.data)
        if (data.type === 'content') handlers.onChunk?.(data.data)
        if (data.type === 'complete') handlers.onDone?.(data.data)
        if (data.type === 'error') handlers.onError?.(data.data)
      }
    }
  }
  run().catch(error => {
    if (error.name !== 'AbortError') handlers.onError?.(error.message)
  })
  return controller
}

export const knowledgeApi = {
  list: (status = 'active', offset = 0) => apiFetch(`/api/knowledge/documents?status=${status}&limit=50&offset=${offset}`),
  upload: file => {
    const form = new FormData(); form.append('file', file)
    return apiFetch('/api/knowledge/documents', { method: 'POST', body: form })
  },
  chunks: (id, offset = 0) => apiFetch(`/api/knowledge/documents/${encodeURIComponent(id)}/chunks?limit=50&offset=${offset}`),
  remove: id => apiFetch(`/api/knowledge/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  restore: id => apiFetch(`/api/knowledge/documents/${encodeURIComponent(id)}/restore`, { method: 'POST' }),
  rebuild: () => apiFetch('/api/knowledge/rebuild', { method: 'POST' }),
}
