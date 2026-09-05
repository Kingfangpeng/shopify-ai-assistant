import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, setCsrfToken, streamChat, streamOps } from './client.js'

describe('统一 API 客户端', () => {
  beforeEach(() => { vi.restoreAllMocks(); setCsrfToken('csrf-old') })

  it('深度分析传递所选模型，跨 UTF-8 分块恢复计划和重规划', async () => {
    const events = [
      { type: 'plan', plan: ['查询订单'] },
      { type: 'replan', plan: ['补查退款'], revision: 1 },
      { type: 'report', report: '真实报告' },
      { type: 'complete', response: '真实报告', model: 'selected-flash' },
    ]
    const bytes = new TextEncoder().encode(events.map(event => `data: ${JSON.stringify(event)}\r\n\r\n`).join(''))
    const body = new ReadableStream({ start(controller) {
      for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7))
      controller.close()
    } })
    const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(body))
    const onTrace = vi.fn(), onReport = vi.fn()
    const result = await new Promise((resolve, reject) => streamOps('session', '深度分析', {
      model: 'selected-flash', onTrace, onReport, onDone: resolve, onError: reject,
    }))
    expect(request.mock.calls[0][0]).toBe('/api/ops')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ session_id: 'session', question: '深度分析', model: 'selected-flash' })
    expect(request.mock.calls[0][1].credentials).toBe('include')
    expect(onTrace).toHaveBeenCalledTimes(2)
    expect(onReport).toHaveBeenCalledWith('真实报告')
    expect(result.model).toBe('selected-flash')
  })

  it('深度分析没有 complete 的断流必须失败', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('data: {"type":"plan","plan":["查询"]}\n\n'))
    const onDone = vi.fn()
    const error = await new Promise(resolve => streamOps('session', '分析', { onDone, onError: resolve }))
    expect(error).toContain('连接提前中断')
    expect(onDone).not.toHaveBeenCalled()
  })

  it('SSE 错误只回调一次，忽略后续假完成', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      'data: {"type":"error","message":"失败"}\n\ndata: {"type":"complete","response":"假成功"}\n\n'))
    const onDone = vi.fn(), onError = vi.fn()
    await new Promise(resolve => streamOps('session', '分析', {
      onDone, onError: value => { onError(value); resolve() },
    }))
    expect(onDone).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('深度分析 CSRF 刷新后仅重试一次', async () => {
    const request = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"error":{"code":"csrf_rejected"}}', { status: 403 }))
      .mockResolvedValueOnce(new Response('{"csrf_token":"new-csrf"}'))
      .mockResolvedValueOnce(new Response('data: {"type":"complete","response":"报告"}\n\n'))
    await new Promise((resolve, reject) => streamOps('session', '分析', { onDone: resolve, onError: reject }))
    expect(request).toHaveBeenCalledTimes(3)
    expect(request.mock.calls[2][1].headers['X-CSRF-Token']).toBe('new-csrf')
  })

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
      streamChat('session-1', '问题', { model: 'deepseek-v4-pro', onDone: resolve, onError: reject })
    })
    expect(result).toBe('完成')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2][1].headers['X-CSRF-Token']).toBe('csrf-new')
    expect(JSON.parse(fetchMock.mock.calls[2][1].body).model).toBe('deepseek-v4-pro')
  })

  it('SSE 将工具调用轨迹和完成元数据交给页面', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response([
      'data: {"type":"tool","data":{"name":"get_orders_summary","status":"running"}}',
      '',
      'data: {"type":"tool","data":{"name":"get_orders_summary","status":"complete"}}',
      '',
      'data: {"type":"content","data":"今天 6 单"}',
      '',
      'data: {"type":"complete","data":{"source":"shopify_graphql","tools":["get_orders_summary"]}}',
      '',
    ].join('\r\n'), { status: 200 }))
    const onTool = vi.fn()
    const onChunk = vi.fn()
    const completed = await new Promise((resolve, reject) => {
      streamChat('session-1', '今天出了几单', {
        onTool,
        onChunk,
        onDone: resolve,
        onError: reject,
      })
    })
    expect(onTool).toHaveBeenNthCalledWith(1, { name: 'get_orders_summary', status: 'running' })
    expect(onTool).toHaveBeenNthCalledWith(2, { name: 'get_orders_summary', status: 'complete' })
    expect(onChunk).toHaveBeenCalledWith('今天 6 单')
    expect(completed).toEqual({ source: 'shopify_graphql', tools: ['get_orders_summary'] })
  })

  it('SSE 将知识库降级警告交给页面且继续完成回答', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response([
      'data: {"type":"warning","data":{"code":"knowledge_unavailable","message":"已切换为仅模型回答"}}',
      '',
      'data: {"type":"content","data":"仍可回答"}',
      '',
      'data: {"type":"complete","data":{"source":"model_only","warnings":["已切换为仅模型回答"]}}',
      '',
    ].join('\r\n'), { status: 200 }))
    const onWarning = vi.fn()
    const onChunk = vi.fn()
    const completed = await new Promise((resolve, reject) => {
      streamChat('session-1', '普通问题', {
        onWarning,
        onChunk,
        onDone: resolve,
        onError: reject,
      })
    })
    expect(onWarning).toHaveBeenCalledWith({
      code: 'knowledge_unavailable',
      message: '已切换为仅模型回答',
    })
    expect(onChunk).toHaveBeenCalledWith('仍可回答')
    expect(completed.source).toBe('model_only')
  })
})
