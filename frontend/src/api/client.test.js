import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, setCsrfToken, streamChat } from './client.js'

describe('统一 API 客户端', () => {
  beforeEach(() => { vi.restoreAllMocks(); setCsrfToken('csrf-old') })

  it('非 GET 请求携带 Cookie 和 CSRF', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))
    await apiFetch('/api/example', { method: 'POST', body: '{}' })
    const options = fetchMock.mock.calls[0][1]
    expect(options.credentials).toBe('include')
    expect(options.headers.get('X-CSRF-Token')).toBe('csrf-old')
  })

  it('CSRF 失效时刷新会话且只重试一次', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'csrf_rejected', message: '失效' } }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: { username: 'king' }, csrf_token: 'csrf-new' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    const result = await apiFetch('/api/example', { method: 'POST' })
    expect(result.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2][1].headers.get('X-CSRF-Token')).toBe('csrf-new')
  })

  it('SSE 遇到 CSRF 失效时刷新后重试', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'csrf_rejected', message: '失效' } }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: { username: 'king' }, csrf_token: 'csrf-new' }), { status: 200 }))
      .mockResolvedValueOnce(new Response('data: {"type":"complete","data":"完成"}\r\n\r\n', { status: 200 }))
    const result = await new Promise((resolve, reject) => {
      streamChat('session-1', '问题', { onDone: resolve, onError: reject })
    })
    expect(result).toBe('完成')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2][1].headers['X-CSRF-Token']).toBe('csrf-new')
  })
})
