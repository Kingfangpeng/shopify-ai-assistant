import { useEffect, useRef, useState } from 'react'
import { Bot, Database, RotateCcw, Send, Square, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { streamChat } from '../api/client.js'

const prompts = ['总结最近上传的产品资料', '为热销产品梳理三个核心卖点', '设计一份低库存处理清单']

export default function Chat({ session, onComplete }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('')
  const [lastQuestion, setLastQuestion] = useState('')
  const abortRef = useRef(null)
  const bottomRef = useRef(null)
  useEffect(() => { setMessages(session?.messages || []) }, [session])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, status])
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = text => {
    const question = (text ?? input).trim()
    if (!question || running || !session?.id) return
    setLastQuestion(question); setInput(''); setRunning(true); setStatus('正在连接知识库…')
    setMessages(items => [...items, { role: 'user', content: question }, { role: 'assistant', content: '', streaming: true }])
    abortRef.current = streamChat(session.id, question, {
      onStatus: setStatus,
      onChunk: chunk => setMessages(items => items.map((item, index) => index === items.length - 1 ? { ...item, content: item.content + chunk } : item)),
      onDone: async () => { setRunning(false); setStatus(''); await onComplete?.() },
      onError: message => {
        setRunning(false); setStatus('')
        setMessages(items => items.map((item, index) => index === items.length - 1 ? { ...item, streaming: false, failed: true, content: item.content || message || '回答生成失败' } : item))
      },
    })
  }
  const stop = () => { abortRef.current?.abort(); setRunning(false); setStatus('已停止生成') }

  if (!session) return <div className="screen-loader">正在加载对话…</div>
  return <div className="page chat-page">
    <header className="page-header"><div><p className="eyebrow">KNOWLEDGE CHAT</p><h1>{session.title || '新对话'}</h1></div><span className="source-pill"><Database size={14} /> 本地知识库 + 模型</span></header>
    <section className="conversation" aria-live="polite">
      {!messages.length && <div className="chat-empty"><span><Bot size={28} /></span><h2>今天要推进什么？</h2><p>我会参考本地知识库回答，并明确标注资料不足的地方。</p><div>{prompts.map(item => <button key={item} onClick={() => send(item)}>{item}</button>)}</div></div>}
      {messages.map((message, index) => <article className={`message ${message.role}`} key={message.id || index}>
        <div className="avatar">{message.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
        <div className="message-content"><p className="message-label">{message.role === 'user' ? '你' : '运营助手'}</p>
          <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (message.streaming ? ' ' : '')}</ReactMarkdown>{message.streaming && <span className="typing-caret" />}</div>
          {message.failed && <button className="retry-link" onClick={() => send(lastQuestion)}><RotateCcw size={13} />重试</button>}
        </div>
      </article>)}
      {status && <div className="chat-status"><span className="loader-dot" />{status}</div>}
      <div ref={bottomRef} />
    </section>
    <footer className="composer-wrap"><div className="composer">
      <textarea aria-label="输入问题" value={input} onChange={e => setInput(e.target.value)} placeholder="询问产品、客服、库存或运营策略…" rows={1}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
      {running ? <button className="stop-button" onClick={stop} aria-label="停止生成"><Square size={15} /></button> : <button className="send-button" onClick={() => send()} disabled={!input.trim()} aria-label="发送"><Send size={16} /></button>}
    </div><p>Enter 发送 · Shift + Enter 换行 · 文档内容按不可信资料处理</p></footer>
  </div>
}
