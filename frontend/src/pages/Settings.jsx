import { useEffect, useState } from 'react'
import { fetchHealth, fetchConfig } from '../api/client.js'
import StatusBadge from '../components/StatusBadge.jsx'
import { Database, Bot, Store, Megaphone, RefreshCw, Info } from 'lucide-react'

export default function Settings({ systemOk }) {
  const [health, setHealth]   = useState(null)
  const [cfg, setCfg]         = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [h, c] = await Promise.all([fetchHealth(), fetchConfig()])
      setHealth(h)
      setCfg(c)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const milvusOk = health?.data?.milvus?.status === 'connected'

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-slate-800">设置</h1>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      <div className="space-y-4">

        {/* 系统状态卡 */}
        <Card icon={<Database size={18} className="text-brand-500" />} title="系统状态">
          <Row label="Milvus 向量库">
            <StatusBadge ok={milvusOk} label={milvusOk ? '已连接' : '未连接'} />
          </Row>
          <Row label="整体状态">
            <StatusBadge ok={systemOk} label={systemOk ? '正常运行' : '存在异常'} />
          </Row>
          {health?.data?.version && (
            <Row label="版本">{health.data.version}</Row>
          )}
          {cfg?.milvus_collection && (
            <Row label="Collection">{cfg.milvus_collection}</Row>
          )}
        </Card>

        {/* AI 模型卡 */}
        <Card icon={<Bot size={18} className="text-brand-500" />} title="AI 模型">
          <Row label="对话模型">
            {cfg ? (
              <span className="font-mono text-sm bg-slate-100 px-2 py-0.5 rounded">{cfg.llm_model}</span>
            ) : <Skeleton />}
          </Row>
          <Row label="Embedding 模型">
            {cfg ? (
              <span className="font-mono text-sm bg-slate-100 px-2 py-0.5 rounded">{cfg.embedding_model}</span>
            ) : <Skeleton />}
          </Row>
          <Row label="知识库召回 Top-K">
            {cfg ? cfg.rag_top_k : <Skeleton />}
          </Row>
        </Card>

        {/* Shopify 卡 */}
        <Card icon={<Store size={18} className="text-brand-500" />} title="Shopify 店铺">
          <Row label="连接状态">
            {cfg ? (
              <StatusBadge ok={cfg.shopify_configured} label={cfg.shopify_configured ? '已配置' : '未配置'} />
            ) : <Skeleton />}
          </Row>
          {cfg?.shopify_domain && (
            <Row label="店铺域名">
              <span className="text-sm text-slate-600">{cfg.shopify_domain}</span>
            </Row>
          )}
        </Card>

        {/* 广告平台卡 */}
        <Card icon={<Megaphone size={18} className="text-brand-500" />} title="广告平台">
          <Row label="Facebook Ads">
            {cfg ? (
              <StatusBadge ok={cfg.facebook_configured} label={cfg.facebook_configured ? '已配置' : '未配置'} />
            ) : <Skeleton />}
          </Row>
          <Row label="Google Ads">
            {cfg ? (
              <StatusBadge ok={cfg.google_configured} label={cfg.google_configured ? '已配置' : '未配置'} />
            ) : <Skeleton />}
          </Row>
        </Card>

        {/* 配置说明卡 */}
        <Card icon={<Info size={18} className="text-amber-500" />} title="如何配置">
          <div className="text-sm text-slate-600 space-y-2 leading-relaxed">
            <p>所有配置项通过服务器上的 <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">.env</code> 文件管理，修改后重启服务即可生效。</p>
            <div className="bg-slate-50 rounded-lg p-3 space-y-1 font-mono text-xs text-slate-700">
              <p className="text-slate-400"># 切换大模型</p>
              <p>LLM_API_KEY=sk-your-key</p>
              <p>LLM_MODEL=gpt-4o</p>
              <div className="border-t border-slate-200 pt-1 mt-1">
                <p className="text-slate-400"># Shopify 配置</p>
                <p>SHOPIFY_STORE_DOMAIN=your-store.myshopify.com</p>
                <p>SHOPIFY_ACCESS_TOKEN=shpat_xxx</p>
              </div>
            </div>
            <p className="text-xs text-slate-400">API Key 不会在此页面显示，仅展示是否已配置。</p>
          </div>
        </Card>

      </div>
    </div>
  )
}

function Card({ icon, title, children }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-slate-100">
        {icon}
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
      </div>
      <div className="px-5 py-3 divide-y divide-slate-50">
        {children}
      </div>
    </div>
  )
}

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm text-slate-800">{children}</span>
    </div>
  )
}

function Skeleton() {
  return <span className="inline-block w-24 h-4 bg-slate-200 rounded animate-pulse" />
}
