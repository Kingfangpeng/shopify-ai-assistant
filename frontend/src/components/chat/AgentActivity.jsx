import { Bot, CheckCircle2, Circle, Database, GitBranch, LoaderCircle, ShieldCheck, Store, Wrench } from 'lucide-react'

const STAGE_LABELS = {
  model_call_started: '模型调用',
  model_call_completed: '模型调用',
  model_call_failed: '模型调用',
  route_completed: '数据来源判断',
  retrieval_started: '知识库检索',
  retrieval_completed: '知识库检索',
  rerank_completed: '候选精排',
  evidence_selected: '证据选择',
  tool_started: '业务工具',
  tool_completed: '业务工具',
  citation_checked: '引用校验',
}

const iconFor = event => {
  if (event.operation === 'retriever' || event.stage?.startsWith('retrieval')) return <Database size={15} />
  if (event.operation === 'reranker') return <GitBranch size={15} />
  if (event.operation === 'tool' || event.type === 'step_complete') return <Wrench size={15} />
  if (event.operation === 'guardrail') return <ShieldCheck size={15} />
  if (event.operation === 'llm') return <Bot size={15} />
  if (event.status === 'running') return <LoaderCircle className="spin" size={15} />
  if (event.status === 'failed') return <Circle size={15} />
  return <CheckCircle2 size={15} />
}

const eventTitle = event => {
  if (event.type === 'plan') return '初始计划'
  if (event.type === 'replan') return `重规划 · 第 ${event.revision || 1} 次调整`
  if (event.type === 'step_start') return `步骤 ${event.step || ''} · 执行中`
  if (event.type === 'step_complete') return `步骤 ${event.step || ''} · ${event.current_step || (event.status === 'failed' ? '失败' : '完成')}`
  return STAGE_LABELS[event.stage] || event.message || '执行活动'
}

export default function AgentActivity({ metadata, status, streaming }) {
  const events = (metadata?.trace || []).filter(event => event && typeof event === 'object')
  if (!events.length && !streaming) return null
  const state = status === 'failed' ? '执行失败' : status === 'interrupted' ? '执行已中断' : streaming ? '执行中' : '执行已完成'
  const deepState = status === 'failed' ? '分析失败' : status === 'interrupted' ? '分析已中断' : streaming ? '分析中' : '分析已完成'
  return <details className="activity-trace" open={streaming || undefined}>
    <summary><span><Store size={15} /><b>执行过程</b><small>{metadata?.mode === 'deep' ? `深度分析 · ${deepState}` : `${events.length} 条活动 · ${state}`}</small></span><span className="trace-expand">查看过程</span></summary>
    <div className="activity-timeline">
      {!events.length && <p className="trace-waiting">正在准备执行信息…</p>}
      {events.map((event, index) => <div className={`activity-event ${event.status || ''}`} key={`${event.stage || event.type}-${index}`}>
        <span className="activity-icon">{iconFor(event)}</span>
        <div>
          <b>{eventTitle(event)}</b>
          {event.message && event.message !== eventTitle(event) && <p>{event.message}</p>}
          {event.plan && <ol>{event.plan.map((step, i) => <li key={i}>{step}</li>)}</ol>}
          {event.current_step && <p>{event.current_step}</p>}
          {event.result_preview && <p className="activity-preview">{event.result_preview}</p>}
          <div className="activity-meta">
            {event.route && <span>路由 {event.route}</span>}
            {event.strategy && <span>{event.strategy}</span>}
            {event.candidates !== undefined && <span>候选 {event.candidates}</span>}
            {event.selected !== undefined && <span>采用 {event.selected}</span>}
            {event.duration_ms !== undefined && <span>{event.duration_ms} ms</span>}
            {event.files?.map(file => <span key={file}>{file}</span>)}
          </div>
          {event.decision && <small className="activity-decision">{event.decision}</small>}
        </div>
      </div>)}
    </div>
  </details>
}
