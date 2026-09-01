import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Send, StopCircle, Bot, User, Loader2 } from 'lucide-react'
import { streamChat } from '../api/client.js'

const QUICK_PROMPTS = [
  '帮我写3个Facebook广告文案',
  '分析这款产品的核心卖点',
  '如何回复客户的退款请求？',
  '黑五活动促销方案建议',
]

// 状态文案映射
const STATUS_LABELS = {
  retrieving: '正在检索知识库...',
  generating: '正在生成回答...',
  tool_call:  '正在调用工具...',
}

export default function Chat({ session, onUpdate }) {
  const [messages, setMessages]   = useState(session?.messages ?? [])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [status, setStatus]       = useState('')   // retrieving | generating | tool_call | ''
  const abortRef                  = useRef(null)
  const bottomRef                 = useRef(null)
  const textareaRef               = useRef(null)
  const sessionId                 = session?.id

  // 当 session 切换时同步 messages
  useEffect(() => {
    setMessages(session?.messages ?? [])
  }, [session?.id]) // eslint-disable-line

  // 自动滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, status])

  // 持久化到父组件
  const persist = useCallback((msgs) => {
    onUpdate?.(msgs)
  }, [onUpdate])

  const send = useCallback(async (text) => {
    const q = (text ?? input).trim()
    if (!q || loading) return

    setInput('')
    setLoading(true)
    setStatus('retrieving')

    const userMsg = { role: 'user', content: q }
    const aiMsg   = { role: 'assistant', content: '', streaming: true }
    const newMsgs = [...messages, userMsg, aiMsg]
    setMessages(newMsgs)
    persist(newMsgs)

    let accumulated = ''
    let finalMsgs = newMsgs

    abortRef.current = streamChat(sessionId, q, {
      onStatus: (s) => {
        setStatus(s)
      },
      onChunk: (chunk) => {
        setStatus('generating')
        accumulated += chunk
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = { role: 'assistant', content: accumulated, streaming: true }
          finalMsgs = next
          return next
        })
      },
      onDone: () => {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = { role: 'assistant', content: accumulated, streaming: false }
          finalMsgs = next
          persist(next)
          return next
        })
        setLoading(false)
        setStatus('')
        abortRef.current = null
      },
      onError: (err) => {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = {
            role: 'assistant',
            content: `出错了：${err || '请求失败，请检查服务是否运行'}`,
            error: true,
          }
          persist(next)
          return next
        })
        setLoading(false)
        setStatus('')
        abortRef.current = null
      },
    })
  }, [input, loading, messages, sessionId, persist])

  const stop = () => {
    abortRef.current?.abort()
    setLoading(false)
    setStatus('')
    setMessages(prev => {
      const next = [...prev]
      if (next[next.length - 1]?.streaming) {
        next[next.length - 1] = { ...next[next.length - 1], streaming: false }
      }
      persist(next)
      return next
    })
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="flex flex-col h-screen md:h-[calc(100vh)] max-h-screen">
      {/* 顶部栏 */}
      <div className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-200 shrink-0">
        <h1 className="text-[15px] font-semibold text-slate-800 truncate max-w-[60%]">
          {session?.title || 'AI 问答'}
        </h1>
      </div>

      {/* 消息区 */}
      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 space-y-4">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}

        {/* 状态指示器 */}
        {loading && status && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center shrink-0 mt-0.5">
              <Bot size={15} className="text-brand-500" />
            </div>
            <div className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-2xl rounded-tl-sm shadow-sm text-sm text-slate-500">
              <Loader2 size={14} className="animate-spin text-brand-500" />
              {STATUS_LABELS[status] || status || '处理中...'}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 快捷提问 */}
      {messages.length <= 1 && !loading && (
        <div className="px-4 md:px-6 pb-2 flex gap-2 flex-wrap">
          {QUICK_PROMPTS.map(p => (
            <button
              key={p}
              onClick={() => send(p)}
              className="text-xs px-3 py-1.5 rounded-full border border-slate-200 bg-white text-slate-600 hover:border-brand-400 hover:text-brand-600 transition-colors"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {/* 输入区 */}
      <div className="px-4 md:px-6 py-3 bg-white border-t border-slate-200 shrink-0">
        <div className="flex items-end gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100 transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="输入你的问题... (Enter 发送，Shift+Enter 换行)"
            disabled={loading}
            className="flex-1 bg-transparent text-sm text-slate-800 placeholder:text-slate-400 resize-none outline-none max-h-32 leading-relaxed py-0.5"
            style={{ height: 'auto' }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = e.target.scrollHeight + 'px'
            }}
          />
          {loading ? (
            <button
              onClick={stop}
              className="shrink-0 p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-50 transition-colors"
            >
              <StopCircle size={20} />
            </button>
          ) : (
            <button
              onClick={() => send()}
              disabled={!input.trim()}
              className="shrink-0 p-1.5 rounded-lg bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={16} />
            </button>
          )}
        </div>
        <p className="text-xs text-slate-400 mt-1.5 text-center">AI 回答基于知识库内容，请上传相关文档以获得更准确的回答</p>
      </div>
    </div>
  )
}

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
        isUser ? 'bg-brand-500' : 'bg-slate-100'
      }`}>
        {isUser
          ? <User size={15} className="text-white" />
          : <Bot size={15} className="text-brand-500" />
        }
      </div>

      <div className={`max-w-[80%] md:max-w-[70%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? 'bg-brand-500 text-white rounded-tr-sm'
            : msg.error
              ? 'bg-red-50 text-red-600 border border-red-200 rounded-tl-sm'
              : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm'
        }`}>
          {isUser ? (
            <p className="whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <div className="markdown-body prose prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content || (msg.streaming ? '▍' : '')}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
