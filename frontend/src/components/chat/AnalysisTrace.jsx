import { CheckCircle2, Circle, GitBranch, ListChecks, LoaderCircle, OctagonAlert } from 'lucide-react'

export default function AnalysisTrace({ metadata, status, streaming }) {
  const trace = metadata?.trace || []
  const finished = trace.filter(event => event.type === 'step_complete')
  const completedIds = new Set(finished.map(event => event.step))
  const revisions = trace.filter(event => event.type === 'replan').length
  const label = streaming ? '分析进行中' : status === 'complete' ? '分析已完成' : status === 'failed' ? '分析失败' : '分析已中断'
  const visible = trace.filter(event => ['plan', 'replan', 'step_complete', 'error'].includes(event.type)
    || (event.type === 'step_start' && !completedIds.has(event.step)))
  return <details className="analysis-trace" open={streaming || undefined}>
    <summary><ListChecks size={17} /><span><b>深度分析 · {label}</b><small>{finished.length} 步已执行{revisions > 0 && ` · ${revisions} 次重规划`} · {metadata?.model}</small></span><span className="trace-expand">查看过程</span></summary>
    <div className="analysis-timeline">
      {!visible.length && <p className="trace-waiting">正在准备计划，尚未取得业务数据。</p>}
      {visible.map((event, index) => <div className={`trace-event ${event.type} ${event.status || ''}`} key={index}>
        <span className="trace-icon">{event.type === 'replan' ? <GitBranch size={15} /> : event.type === 'step_complete' ? event.status === 'failed' ? <OctagonAlert size={15} /> : <CheckCircle2 size={15} /> : event.type === 'step_start' && streaming ? <LoaderCircle className="spin" size={15} /> : <Circle size={15} />}</span>
        <div>{event.plan ? <><b>{event.type === 'replan' ? `重规划 · 第 ${event.revision || 1} 次调整` : '初始计划'}</b><ol>{event.plan.map((step, i) => <li key={i}>{step}</li>)}</ol></>
          : <><b>{event.step ? `步骤 ${event.step} · ` : ''}{event.current_step || event.message}</b>
            {event.type === 'step_start' && <small>{streaming ? '执行中…' : '中止于此步骤'}</small>}
            {event.status === 'failed' && <small>该步骤未取得可用结果</small>}
            {event.result_preview && <p>{event.result_preview}</p>}</>}
        </div>
      </div>)}
    </div>
  </details>
}
