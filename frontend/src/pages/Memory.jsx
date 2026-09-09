import { useEffect, useState } from 'react'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { memoryApi } from '../api/client.js'

const tabs = [
  ['candidate', '待确认'],
  ['active', '有效记忆'],
  ['history', '历史版本'],
]

const kindLabels = {
  preference: '偏好',
  business_rule: '业务规则',
  shop_context: '店铺事实',
  goal: '目标',
}

export default function Memory() {
  const [tab, setTab] = useState('candidate')
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const load = async nextTab => {
    const mode = nextTab || tab
    setBusy('loading')
    try {
      const statuses = mode === 'history' ? ['superseded', 'rejected', 'expired'] : [mode]
      const pages = await Promise.all(statuses.map(status => memoryApi.list(status)))
      setItems(pages.flatMap(page => page.items || []))
    } catch (error) {
      setNotice({ type: 'error', text: error.message })
    } finally {
      setBusy('')
    }
  }

  useEffect(() => { load(tab) }, [tab]) // eslint-disable-line

  const act = async (id, action) => {
    setBusy(id)
    try {
      await action()
      setNotice({ type: 'success', text: '记忆状态已更新' })
      await load()
    } catch (error) {
      setNotice({ type: 'error', text: error.message })
    } finally {
      setBusy('')
    }
  }

  const edit = item => {
    const value = window.prompt('修改记忆内容', item.value)
    if (value && value.trim() && value.trim() !== item.value) {
      act(item.id, () => memoryApi.edit(item.id, { value: value.trim() }))
    }
  }

  const create = () => {
    const memoryKey = window.prompt('记忆键（小写英文 snake_case）')
    if (!memoryKey) return
    const value = window.prompt('记忆内容')
    if (!value) return
    act('create', () => memoryApi.create({
      memory_key: memoryKey.trim(),
      kind: 'preference',
      value: value.trim(),
    }))
  }

  return <div className="page knowledge-page memory-page">
    <header className="page-header">
      <div>
        <p className="eyebrow">CONTROLLED CONTEXT</p>
        <h1>长期记忆</h1>
        <p>模型提取的内容先进入候选；只有你确认后，才会在新对话中使用。</p>
      </div>
      <button className="primary-button" onClick={create} disabled={!!busy}>
        <Plus size={16} />手动添加
      </button>
    </header>

    {notice && <div className={'notice ' + notice.type} role="status">
      <span>{notice.text}</span><button onClick={() => setNotice(null)}><X size={15} /></button>
    </div>}

    <div className="tab-bar">
      {tabs.map(([value, label]) => <button key={value} className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>
        {label}
      </button>)}
    </div>

    <section className="panel memory-panel">
      <div className="panel-heading">
        <span>{tabs.find(([value]) => value === tab)?.[1]}</span><small>{items.length} 项</small>
      </div>
      {busy === 'loading' && <div className="skeleton-list">{[1, 2, 3].map(value => <span key={value} />)}</div>}
      {busy !== 'loading' && !items.length && <div className="empty-panel"><p>当前没有记录</p></div>}
      {busy !== 'loading' && items.map(item => <article className="memory-row" key={item.id}>
        <div className="memory-row-main">
          <div><span className="status-pill">{kindLabels[item.kind] || item.kind}</span><b>{item.memory_key}</b><small>v{item.version}</small></div>
          <p>{item.value}</p>
          <small>状态：{item.status} · 置信度：{Math.round(item.confidence * 100)}%</small>
        </div>
        <div className="memory-actions">
          {item.status === 'candidate' && <button className="icon-button" disabled={busy === item.id} onClick={() => act(item.id, () => memoryApi.approve(item.id))} aria-label="确认">
            <Check size={16} />
          </button>}
          {(item.status === 'candidate' || item.status === 'active') && <button className="icon-button" disabled={busy === item.id} onClick={() => edit(item)} aria-label="修改">
            <Pencil size={15} />
          </button>}
          {item.status === 'candidate' && <button className="icon-button danger" disabled={busy === item.id} onClick={() => act(item.id, () => memoryApi.reject(item.id))} aria-label="拒绝">
            <X size={16} />
          </button>}
          <button className="icon-button danger" disabled={busy === item.id} onClick={() => {
            if (window.confirm('永久删除这条记忆？')) act(item.id, () => memoryApi.remove(item.id))
          }} aria-label="删除"><Trash2 size={15} /></button>
        </div>
      </article>)}
    </section>
  </div>
}
