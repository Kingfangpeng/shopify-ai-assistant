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
export const fetchModels = (refresh = false) => apiFetch(`/api/models${refresh ? '?refresh=true' : ''}`)

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

export const streamChat = (sessionId, question, handlers = {}) =>
  streamRequest('/api/chat_stream', { session_id: sessionId, question, model: handlers.model || undefined }, handlers)

export const streamOps = (sessionId, question, handlers = {}) =>
  streamRequest('/api/ops', { session_id: sessionId, question, model: handlers.model || undefined }, handlers, true)

function streamRequest(path, payload, handlers, deep = false) {
  const controller = new AbortController()
  let terminal = false
  const fail = error => {
    if (terminal || controller.signal.aborted) return
    terminal = true
    handlers.onError?.(error)
  }
  const run = async (retried = false) => {
    const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }
    const response = await fetch(`${BASE}${path}`, {
      method: 'POST', headers, credentials: 'include',
      body: JSON.stringify(payload), signal: controller.signal,
    })
    if (response.status === 401) window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    if (response.status === 403 && !retried) {
      const body = await response.clone().json().catch(() => ({}))
      if (body?.error?.code === 'csrf_rejected') {
        await refreshCsrf()
        if (!controller.signal.aborted) return run(true)
        return
      }
    }
    if (!response.ok) return parseResponse(response)
    if (!response.body) throw new Error('服务未返回可读数据流')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    const dispatchEvent = event => {
      if (terminal || controller.signal.aborted) return
      const lines = event.split(/\r?\n/).filter(line => line.startsWith('data:'))
      if (!lines.length) return
      const data = JSON.parse(lines.map(line => line.slice(5).trimStart()).join('\n'))
      if (deep) {
        if (['plan', 'replan', 'step_start', 'step_complete', 'status'].includes(data.type)) {
          handlers.onTrace?.(data)
          handlers.onStatus?.(data.message || '')
        }
        if (data.type === 'report') handlers.onReport?.(data.report)
      } else {
        if (data.type === 'status') handlers.onStatus?.(data.data)
        if (data.type === 'tool') handlers.onTool?.(data.data)
        if (data.type === 'warning') handlers.onWarning?.(data.data)
        if (data.type === 'content') handlers.onChunk?.(data.data)
      }
      if (data.type === 'error') fail(deep ? data : data.data)
      if (data.type === 'complete') {
        terminal = true
        handlers.onDone?.(deep ? data : data.data)
      }
    }
    try {
      while (!terminal && !controller.signal.aborted) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split(/\r?\n\r?\n/)
        buffer = events.pop() || ''
        for (const event of events) dispatchEvent(event)
        if (buffer.length > 2_000_000) throw new Error('响应超出安全大小限制')
      }
      buffer += decoder.decode()
      if (buffer.trim()) dispatchEvent(buffer)
      if (!terminal && !controller.signal.aborted) fail('连接提前中断，未收到完成结果，请重试')
    } finally {
      await reader.cancel().catch(() => {})
      reader.releaseLock()
    }
  }
  run().catch(error => {
    if (error.name !== 'AbortError') fail(error.message)
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
