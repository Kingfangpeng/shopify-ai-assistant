import { useEffect, useState } from 'react'
import { Bot, CheckCircle2, Database, RefreshCw, ShieldCheck, Store } from 'lucide-react'
import { fetchConfig, fetchShopifyStatus } from '../api/client.js'

export default function Settings({ user, systemOk }) {
  const [config, setConfig] = useState(null)
  const [shopify, setShopify] = useState(null)
  const [loading, setLoading] = useState(true)
  const load = async () => {
    setLoading(true)
    try {
      const [cfg, status] = await Promise.all([fetchConfig(), fetchShopifyStatus()])
      setConfig(cfg); setShopify(status)
    } catch { setConfig(null) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  return <div className="page settings-page">
    <header className="page-header"><div><p className="eyebrow">LOCAL CONFIGURATION</p><h1>设置与连接</h1><p>只展示非敏感状态，令牌和密钥永不返回浏览器。</p></div><button className="secondary-button" onClick={load} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} />刷新</button></header>
    <div className="settings-grid">
      <StatusCard icon={ShieldCheck} title="本地登录" state={!!user} stateLabel="已保护">
        <Row label="管理员" value={user?.username} /><Row label="会话策略" value="8h / 闲置 60m" /><Row label="Cookie" value="HttpOnly · Strict" />
      </StatusCard>
      <StatusCard icon={Store} title="Shopify GraphQL" state={shopify?.connected} stateLabel={shopify?.connected ? '已连接' : '未连接'}>
        <Row label="API 版本" value={shopify?.api_version || config?.shopify_api_version || '2026-07'} mono />
        <Row label="店铺" value={shopify?.domain || '尚未配置'} /><Row label="Demo" value={shopify?.demo_mode ? '显式开启' : '关闭'} />
      </StatusCard>
      <StatusCard icon={Database} title="本地数据" state={config?.milvus_status === 'connected'} stateLabel={config?.milvus_status === 'connected' ? '向量库已连接' : '向量库未连接'}>
        <Row label="SQLite" value="本机持久化" /><Row label="Collection" value={config?.milvus_collection || '—'} mono /><Row label="服务" value={systemOk ? '正常' : '待检查'} />
      </StatusCard>
      <StatusCard icon={Bot} title="模型与权限" state stateLabel="只读">
        <Row label="对话模型" value={config?.llm_model || '—'} mono /><Row label="Embedding" value={config?.embedding_model || '—'} mono />
        <div className="scope-list"><small>期望 Shopify scopes</small>{['read_orders', 'read_products', 'read_inventory', 'read_customers', 'read_discounts'].map(scope => <span key={scope}><CheckCircle2 size={12} />{scope}</span>)}</div>
      </StatusCard>
    </div>
    <div className="risk-note"><b>剩余本地风险</b><p>Milvus 未启用自身账号鉴权；端口仅绑定 127.0.0.1，但本机其他进程仍可能访问。SQLite、上传文件与向量依赖 Windows 用户权限及 BitLocker/全盘加密。</p></div>
  </div>
}

function StatusCard({ icon: Icon, title, state, stateLabel, children }) { return <section className="setting-card"><header><span><Icon size={18} /></span><div><h2>{title}</h2><small className={state ? 'ok' : ''}><i />{stateLabel}</small></div></header><div>{children}</div></section> }
function Row({ label, value, mono }) { return <div className="setting-row"><span>{label}</span><b className={mono ? 'mono' : ''}>{value || '—'}</b></div> }
