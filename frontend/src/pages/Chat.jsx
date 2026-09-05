import { useEffect, useRef, useState } from 'react'
import { Bot, Database, RefreshCw, RotateCcw, Send, Square, Store, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { fetchModels, streamChat, streamOps } from '../api/client.js'
import AnalysisTrace from '../components/chat/AnalysisTrace.jsx'

const prompts = ['今天出了几单', '总结最近上传的产品资料', '设计一份低库存处理清单']
const MODEL_KEY = 'shopify_ai_selected_model'
const MODE_KEY = 'shopify_ai_chat_mode'
const deepPrompts = ['分析最近7天的经营情况，结合订单、产品销量和退款数据给出建议', '检查库存与销量，找出需要优先处理的商品']
const cleanAssistantContent = content => String(content || '')
  .replace(/<\/?(?:knowledge|untrusted_knowledge|shopify_tool_results)(?:\s[^>]*)?>/gi, '')
  .replace(/^\s*(?:中的内容|知识库(?:中的)?内容|参考资料(?:中的)?内容)[\s\S]{0,240}?(?:与当前问题无关|不相关|不采用|未采用|不使用)[\s\S]{0,80}?[。.!]\s*/i, '')
  .trimStart()
const TOOL_LABELS = {
  compare_order_periods: '订单周期对比',
  get_orders_summary: '订单汇总',
  get_order_list: '订单明细',
  get_abandoned_checkouts: '弃购分析',
  get_inventory_levels: '库存查询',
  get_product_performance: '产品表现',
  get_customer_segments: '客户分层',
  get_refund_stats: '退款统计',
  get_discount_performance: '折扣表现',
  get_traffic_overview: '网站流量',
  get_traffic_timeseries: '流量趋势',
  get_traffic_sources: '流量来源',
  get_landing_page_performance: '落地页表现',
  get_device_traffic: '设备流量',
  get_traffic_geography: '访客地区',
  get_search_performance: '站内搜索',
  get_web_performance: '网页性能',
}

export default function Chat({ session, onComplete }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('')
  const [mode, setMode] = useState(() => localStorage.getItem(MODE_KEY) === 'deep' ? 'deep' : 'chat')
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [modelsLoading, setModelsLoading] = useState(true)
  const [modelWarning, setModelWarning] = useState('')
  const [answerWarning, setAnswerWarning] = useState('')
  const [answerSource, setAnswerSource] = useState('knowledge_and_model')
  const [toolActivity, setToolActivity] = useState([])
  const abortRef = useRef(null)
  const runRef = useRef(0)
  const bottomRef = useRef(null)
  useEffect(() => { setMessages(session?.messages || []) }, [session])
  useEffect(() => {
    setAnswerSource(session?.messages?.findLast(item => item.role === 'assistant')?.metadata?.mode === 'deep' ? 'ops' : 'knowledge_and_model')
    setAnswerWarning(''); setToolActivity([]); setRunning(false); setStatus('')
  }, [session?.id])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, status])
  useEffect(() => () => { runRef.current += 1; abortRef.current?.abort() }, [session?.id])

  const loadModels = async (refresh = false) => {
    setModelsLoading(true)
    try {
      const catalog = await fetchModels(refresh)
      const available = catalog.models || []
      const remembered = localStorage.getItem(MODEL_KEY)
      const configured = available.includes(catalog.default_model) ? catalog.default_model : available[0]
      const next = available.includes(remembered) ? remembered : configured || ''
      setModels(available); setSelectedModel(next); setModelWarning(catalog.warning || '')
      if (next) localStorage.setItem(MODEL_KEY, next)
    } catch (error) {
      setModelWarning(error.message || '模型列表加载失败')
    } finally { setModelsLoading(false) }
  }
  useEffect(() => { loadModels() }, [])

  const chooseModel = event => {
    const value = event.target.value
    setSelectedModel(value); localStorage.setItem(MODEL_KEY, value)
  }

  const send = (text, retry = {}) => {
    const question = (text ?? input).trim()
    if (!question || running || !session?.id) return
    const requestMode = retry.mode || mode
    const requestModel = retry.model || selectedModel
    const sessionId = session.id
    const token = ++runRef.current
    const current = () => runRef.current === token
    const metadata = { mode: requestMode, model: requestModel, trace: [] }
    const updateAnswer = fn => { if (current()) setMessages(items => items.map((item, index) => index === items.length - 1 ? fn(item) : item)) }
    setInput(''); setRunning(true); setStatus(requestMode === 'deep' ? '正在准备深度分析…' : '正在判断数据来源…'); setAnswerWarning(''); setToolActivity([])
    setMessages(items => [...items, { role: 'user', content: question, metadata }, { role: 'assistant', content: '', streaming: true, status: 'running', metadata }])
    abortRef.current = (requestMode === 'deep' ? streamOps : streamChat)(sessionId, question, {
      model: requestModel,
      onStatus: value => { if (current()) setStatus(value) },
      onTrace: event => updateAnswer(item => ({ ...item, metadata: { ...item.metadata, trace: [...item.metadata.trace, event].slice(-80) } })),
      onReport: report => updateAnswer(item => ({ ...item, content: report })),
      onTool: event => {
        if (!current()) return
        setToolActivity(items => {
          const next = items.filter(item => item.name !== event.name)
          return [...next, event]
        })
        setStatus(event.message || '正在调用只读工具…')
      },
      onWarning: warning => {
        if (!current()) return
        const message = typeof warning === 'string' ? warning : warning?.message
        setAnswerWarning(message || '部分数据源暂时不可用')
      },
      onChunk: chunk => updateAnswer(item => ({ ...item, content: item.content + chunk })),
      onDone: async data => {
        if (!current()) return
        updateAnswer(item => ({ ...item, streaming: false, status: 'complete', content: data?.response || data?.answer || item.content }))
        const warning = data?.warnings?.[0]
        if (warning) setAnswerWarning(warning)
        setRunning(false); setStatus(''); setAnswerSource(data?.source || 'knowledge_and_model')
        try { await onComplete?.(sessionId) } catch { if (current()) setAnswerWarning('结果已返回，历史刷新失败，请稍后刷新页面') }
      },
      onError: message => {
        if (!current()) return
        setRunning(false); setStatus('')
        const detail = typeof message === 'string' ? message : message?.message
        updateAnswer(item => ({ ...item, streaming: false, failed: true, status: 'failed', content: detail || item.content || '回答生成失败' }))
      },
    })
  }
  const stop = () => {
    runRef.current += 1
    abortRef.current?.abort()
    setMessages(items => items.map((item, index) => index === items.length - 1 ? { ...item, streaming: false, status: 'interrupted', content: item.content || '已停止生成，可查看已有过程或重新提问。' } : item))
    setRunning(false); setStatus('已停止生成')
  }

  if (!session) return <div className="screen-loader">正在加载对话…</div>
  return <div className="page chat-page">
    <header className="page-header"><div><p className="eyebrow">KNOWLEDGE CHAT</p><h1>{session.title || '新对话'}</h1></div>
      <div className="chat-header-tools">
        <label className="model-picker"><Bot size={14} /><span>模型</span>
          <select aria-label="选择对话模型" value={selectedModel} onChange={chooseModel} disabled={running || modelsLoading || !models.length}>
            {!models.length && <option value="">{modelsLoading ? '加载中…' : '暂无可用模型'}</option>}
            {models.map(model => <option value={model} key={model}>{model}</option>)}
          </select>
        </label>
        <button className="model-refresh" onClick={() => loadModels(true)} disabled={running || modelsLoading} aria-label="刷新模型列表" title="刷新模型列表"><RefreshCw size={14} className={modelsLoading ? 'spin' : ''} /></button>
        <span className="source-pill">
          {answerSource.startsWith('shopify') ? <Store size={14} /> : <Database size={14} />}
          {answerSource === 'shopify_graphql' && 'Shopify 实时数据'}
          {answerSource === 'shopify_graphql_and_knowledge' && 'Shopify + 本地知识库'}
          {answerSource === 'shopify_analytics' && 'Shopify Analytics 实时数据'}
          {answerSource === 'shopify_analytics_and_knowledge' && 'Shopify Analytics + 本地知识库'}
          {answerSource === 'demo' && '演示数据'}
          {answerSource === 'knowledge_and_model' && '本地知识库 + 模型'}
          {answerSource === 'model_only' && '仅模型 · 知识库离线'}
          {answerSource === 'model' && '模型理解 · 未查询业务数据'}
          {answerSource === 'ops' && '只读深度分析'}
        </span>
      </div>
    </header>
    {modelWarning && <div className="model-warning" role="status">{modelWarning}</div>}
    {answerWarning && <div className="model-warning" role="status">{answerWarning}</div>}
    {!!toolActivity.length && <div className="agent-trace" aria-live="polite">
      {toolActivity.map(item => <span key={item.name} className={item.status === 'complete' ? 'complete' : ''}>
        <Store size={12} />{TOOL_LABELS[item.name] || item.name}{item.status === 'complete' ? ' ✓' : '…'}
      </span>)}
    </div>}
    <section className="conversation" aria-live="polite">
      {!messages.length && <div className="chat-empty"><span><Bot size={28} /></span><h2>{mode === 'deep' ? '把问题交给一个完整的分析过程' : '今天要推进什么？'}</h2><p>{mode === 'deep' ? '制定计划、逐步查询、检查结果并调整，最后生成报告。全程只读。' : '按问题查询店铺或本地资料，并明确标注资料不足的地方。'}</p><div>{(mode === 'deep' ? deepPrompts : prompts).map(item => <button disabled={running} key={item} onClick={() => send(item)}>{item}</button>)}</div></div>}
      {messages.map((message, index) => <article className={`message ${message.role}`} key={message.id || index}>
        <div className="avatar">{message.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
        <div className="message-content"><p className="message-label">{message.role === 'user' ? '你' : '运营助手'}</p>
          {message.role === 'assistant' && message.metadata?.mode === 'deep' && <AnalysisTrace metadata={message.metadata} status={message.status} streaming={message.streaming} />}
          <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.role === 'assistant' ? cleanAssistantContent(message.content) || (message.streaming ? ' ' : '') : message.content}</ReactMarkdown>{message.streaming && <span className="typing-caret" />}</div>
          {(message.failed || ['failed', 'interrupted'].includes(message.status)) && <button className="retry-link" disabled={running} onClick={() => send(messages.slice(0, index).findLast(item => item.role === 'user')?.content || '', message.metadata || {})}><RotateCcw size={13} />重试</button>}
        </div>
      </article>)}
      {status && <div className="chat-status"><span className="loader-dot" />{status}</div>}
      <div ref={bottomRef} />
    </section>
    <footer className="composer-wrap"><div className="composer-mode-row">
      <div className="mode-switch" role="group" aria-label="回答模式">
        {[['chat', '普通问答'], ['deep', '深度分析']].map(([value, label]) => <button key={value} aria-pressed={mode === value} disabled={running} onClick={() => { setMode(value); localStorage.setItem(MODE_KEY, value) }}>{label}</button>)}
      </div><span>{mode === 'deep' ? '计划 → 执行 → 检查 / 重规划 → 报告 · 多次模型调用' : '按需查询 · 快速回答'}</span>
    </div><div className="composer">
      <textarea aria-label="输入问题" value={input} onChange={e => setInput(e.target.value)} placeholder="询问产品、客服、库存或运营策略…" rows={1}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
      {running ? <button className="stop-button" onClick={stop} aria-label="停止生成"><Square size={15} /></button> : <button className="send-button" onClick={() => send()} disabled={!input.trim()} aria-label="发送"><Send size={16} /></button>}
    </div><p>Enter 发送 · Shift + Enter 换行 · 文档内容按不可信资料处理</p></footer>
  </div>
}
