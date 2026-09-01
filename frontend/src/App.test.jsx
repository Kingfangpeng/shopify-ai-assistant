import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import App from './App.jsx'

beforeEach(() => {
  window.history.pushState({}, '', '/')
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    error: { code: 'authentication_required', message: '请先登录', request_id: 'test' },
  }), { status: 401, headers: { 'Content-Type': 'application/json' } }))
})

it('未登录用户只能看到管理员登录页', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: '登录运营台' })).toBeInTheDocument()
  expect(screen.getByLabelText('密码')).toHaveAttribute('type', 'password')
})
