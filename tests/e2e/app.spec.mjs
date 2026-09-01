import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { expect, test } = require('@playwright/test')

const fixture = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'product.md')

test('登录、知识库、多轮聊天、回收站与登出完整流程', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('用户名').fill('king')
  await page.getByLabel('密码').fill('Local-QA-Password-2026')
  await page.getByRole('button', { name: '进入运营台' }).click()
  await expect(page).toHaveURL(/\/chat$/)

  await page.getByRole('link', { name: '知识库' }).click()
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: '上传文档' }).click()
  await (await chooser).setFiles(fixture)
  await expect(page.getByText('product.md 已安全索引')).toBeVisible()
  await page.getByRole('button', { name: /product\.md 1 个分片/ }).click()
  await expect(page.getByText(/24 小时保冷/)).toBeVisible()

  await page.getByRole('button', { name: '新对话', exact: true }).click()
  await page.getByLabel('输入问题').fill('Aurora 保温杯适合哪类客户？')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText(/当前会话包含 0 条历史消息/)).toBeVisible()
  await page.getByLabel('输入问题').fill('它的核心卖点是什么？')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText(/当前会话包含 2 条历史消息/)).toBeVisible()

  await page.getByRole('link', { name: '知识库' }).click()
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '移入回收站' }).click()
  await expect(page.getByText('文档已移入回收站')).toBeVisible()
  await page.getByRole('button', { name: '回收站' }).click()
  await page.getByRole('button', { name: '恢复' }).click()
  await expect(page.getByText('文档已恢复并重新索引')).toBeVisible()

  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login$/)
})
