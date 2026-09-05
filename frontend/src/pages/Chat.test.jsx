import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import Chat from './Chat.jsx'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

it('聊天页展示服务商模型列表并记住选择', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    models: ['deepseek-v4-flash', 'deepseek-v4-pro'],
    default_model: 'deepseek-v4-pro',
    provider: 'api.deepseek.com',
    warning: null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  const user = userEvent.setup()
  render(<Chat session={{ id: 'session-1', title: '新对话', messages: [] }} />)
  const picker = await screen.findByLabelText('选择对话模型')
  expect(picker).toHaveValue('deepseek-v4-pro')
  await user.selectOptions(picker, 'deepseek-v4-flash')
  expect(localStorage.getItem('shopify_ai_selected_model')).toBe('deepseek-v4-flash')
})

it('历史回答不会显示内部 knowledge 标记和元话术', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    models: ['local-model'], default_model: 'local-model', warning: null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  render(<Chat session={{
    id: 'session-1',
    title: '新对话',
    messages: [{ role: 'assistant', content: '<knowledge> 中的内容与当前问题无关，因此不采用。\n关于订单：真实结果如下。' }],
  }} />)
  expect(await screen.findByText('关于订单：真实结果如下。')).toBeInTheDocument()
  expect(screen.queryByText(/中的内容与当前问题无关/)).not.toBeInTheDocument()
  expect(document.body.textContent).not.toContain('<knowledge>')
})

const catalogResponse = () => new Response(JSON.stringify({ models: ['flash', 'pro'], default_model: 'pro' }))
const session = { id: 'session-1', title: '测试', messages: [] }

it('深度模式显示计划和重规划并传递当前模型', async () => {
  const request = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => url === '/api/models' ? catalogResponse() : new Response([
    { type: 'plan', plan: ['查询订单', '查询库存'] },
    { type: 'step_complete', step: 1, current_step: '查询订单', result_preview: '取得订单结果' },
    { type: 'replan', revision: 1, plan: ['补查退款'] },
    { type: 'report', report: '本次分析报告' },
    { type: 'complete', response: '本次分析报告', model: 'flash' },
  ].map(event => `data: ${JSON.stringify(event)}\n\n`).join('')))
  const user = userEvent.setup()
  render(<Chat session={session} />)
  await waitFor(() => expect(screen.getByLabelText('选择对话模型')).toHaveValue('pro'))
  await user.selectOptions(screen.getByLabelText('选择对话模型'), 'flash')
  await user.click(screen.getByRole('button', { name: '深度分析', exact: true }))
  await user.type(screen.getByLabelText('输入问题'), '分析经营')
  await user.click(screen.getByRole('button', { name: '发送', exact: true }))
  expect(await screen.findByText('本次分析报告')).toBeInTheDocument()
  expect(screen.getByText('深度分析 · 分析已完成')).toBeInTheDocument()
  expect(screen.getByText('重规划 · 第 1 次调整')).toBeInTheDocument()
  const call = request.mock.calls.find(([url]) => url === '/api/ops')
  expect(JSON.parse(call[1].body)).toEqual({ question: '分析经营', model: 'flash', session_id: 'session-1' })
})

it('历史深度分析恢复过程，失败重试仍使用原模式和模型', async () => {
  const request = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => url === '/api/models' ? catalogResponse()
    : new Response('data: {"type":"complete","response":"重试报告"}\n\n'))
  const user = userEvent.setup()
  render(<Chat session={{ ...session, messages: [
    { role: 'user', content: '之前的问题' },
    { role: 'assistant', content: '已停止', status: 'interrupted', metadata: {
      mode: 'deep', model: 'flash', trace: [{ type: 'plan', plan: ['查询订单'] }],
    } },
  ] }} />)
  expect(screen.getByText('深度分析 · 分析已中断')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '重试', exact: true }))
  await screen.findByText('重试报告')
  const call = request.mock.calls.find(([url]) => url === '/api/ops')
  expect(JSON.parse(call[1].body).model).toBe('flash')
  expect(JSON.parse(call[1].body).question).toBe('之前的问题')
})

it('停止后忽略迟到事件，切换会话取消旧流', async () => {
  let controller
  const request = vi.spyOn(globalThis, 'fetch').mockImplementation(async url => url === '/api/models' ? catalogResponse()
    : new Response(new ReadableStream({ start(value) { controller = value } })))
  const user = userEvent.setup()
  const view = render(<Chat session={session} />)
  await user.click(screen.getByRole('button', { name: '深度分析', exact: true }))
  await user.type(screen.getByLabelText('输入问题'), '测试停止')
  await user.click(screen.getByRole('button', { name: '发送', exact: true }))
  expect(screen.getByRole('button', { name: '深度分析', exact: true })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '停止生成' }))
  expect(screen.getByText('深度分析 · 分析已中断')).toBeInTheDocument()
  expect(request.mock.calls.find(([url]) => url === '/api/ops')[1].signal.aborted).toBe(true)
  await act(async () => {
    controller.enqueue(new TextEncoder().encode('data: {"type":"report","report":"迟到的内容"}\n\n'))
    controller.close()
  })
  expect(screen.queryByText('迟到的内容')).not.toBeInTheDocument()
  view.rerender(<Chat session={{ id: 'session-2', title: '新的会话', messages: [] }} />)
  expect(screen.queryByText('测试停止')).not.toBeInTheDocument()
})
