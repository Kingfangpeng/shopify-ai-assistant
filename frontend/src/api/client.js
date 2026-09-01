// API 调用封装，所有接口统一从这里调用

const BASE = ''  // 同域，不需要写 host；dev 模式下 vite proxy 转发

// ── 健康检查 ──────────────────────────────────────────────
export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}

// ── 配置信息 ──────────────────────────────────────────────
export async function fetchConfig() {
  const res = await fetch(`${BASE}/api/config`)
  return res.json()
}

// ── 知识库问答（流式 SSE）────────────────────────────────
// onChunk(text) 每次收到一段文字回调
// onDone() 完成回调
// onError(msg) 出错回调
// 返回 AbortController，调用 .abort() 可中断
function normalizeStatus(statusText) {
  if (!statusText) return ''
  if (statusText.includes('检索')) return 'retrieving'
  if (statusText.includes('生成')) return 'generating'
  if (statusText.includes('工具')) return 'tool_call'
  return statusText
}

export function streamChat(sessionId, question, { onStatus, onChunk, onDone, onError }) {
  const controller = new AbortController()

  fetch(`${BASE}/api/chat_stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ Id: sessionId, Question: question }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()  // 最后一行可能不完整，留到下次处理

        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            const evt = JSON.parse(raw)
            if (evt.type === 'status') {
              onStatus?.(normalizeStatus(evt.data))
            } else if (evt.type === 'content') {
              onChunk?.(evt.data)
            } else if (evt.type === 'done') {
              onDone?.()
            } else if (evt.type === 'error') {
              onError?.(evt.data)
            }
          } catch {
            // 忽略解析失败的行
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError?.(err.message)
    })

  return controller
}

// ── 普通问答（非流式）────────────────────────────────────
export async function sendChat(sessionId, question) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ Id: sessionId, Question: question }),
  })
  return res.json()
}

// ── 上传文件到知识库 ─────────────────────────────────────
export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/upload`, {
    method: 'POST',
    body: form,
  })
  return res.json()
}

// ── 重建全部索引 ─────────────────────────────────────────
export async function rebuildIndex() {
  const res = await fetch(`${BASE}/api/index_directory`, {
    method: 'POST',
  })
  return res.json()
}

// ── 清空会话 ─────────────────────────────────────────────
export async function clearSession(sessionId) {
  const res = await fetch(`${BASE}/api/chat/clear`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId }),
  })
  return res.json()
}

// ── 知识库分片查询 ───────────────────────────────────────
export async function fetchChunks({ filename = '', filePath = '', limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (filename) params.set('filename', filename)
  if (filePath) params.set('file_path', filePath)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  const url = `${BASE}/api/knowledge/chunks?${params.toString()}`
  const res = await fetch(url)
  return res.json()
}

// ── 知识库统计 ───────────────────────────────────────────
export async function fetchKnowledgeStats() {
  const res = await fetch(`${BASE}/api/knowledge/stats`)
  return res.json()
}

export async function deleteKnowledgeFile(filePath) {
  const params = new URLSearchParams({ file_path: filePath })
  const res = await fetch(`${BASE}/api/knowledge/file?${params.toString()}`, {
    method: 'DELETE',
  })
  return res.json()
}
