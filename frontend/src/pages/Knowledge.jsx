import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle,
  Eye,
  FileText,
  Layers,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import {
  deleteKnowledgeFile,
  fetchChunks,
  fetchKnowledgeStats,
  rebuildIndex,
  uploadFile,
} from '../api/client.js'

const STORAGE_KEY = 'shopify_ai_files'
const PAGE_SIZE = 50

function loadFiles() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

function saveFiles(files) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(files))
}

export default function Knowledge() {
  const [files, setFiles] = useState(loadFiles)
  const [stats, setStats] = useState({ total_chunks: 0, files: [] })
  const [chunks, setChunks] = useState([])
  const [selectedFile, setSelectedFile] = useState('')
  const [selectedChunk, setSelectedChunk] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [uploads, setUploads] = useState({})
  const [loadingChunks, setLoadingChunks] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [message, setMessage] = useState(null)
  const inputRef = useRef(null)

  const indexedFiles = useMemo(() => stats.files || [], [stats.files])

  const loadKnowledge = useCallback(async (filename = selectedFile) => {
    setLoadingChunks(true)
    setMessage(null)
    try {
      const [statsRes, chunksRes] = await Promise.all([
        fetchKnowledgeStats(),
        fetchChunks({ filename, limit: PAGE_SIZE, offset: 0 }),
      ])

      if (statsRes.code === 200) setStats(statsRes.data || { total_chunks: 0, files: [] })
      if (chunksRes.code === 200) setChunks(chunksRes.data?.chunks || [])
    } catch {
      setMessage({ ok: false, text: '知识库数据加载失败，请确认后端和 Milvus 正在运行。' })
    } finally {
      setLoadingChunks(false)
    }
  }, [selectedFile])

  useEffect(() => {
    loadKnowledge('')
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const addFile = (name) => {
    const entry = { name, time: new Date().toLocaleString('zh-CN') }
    setFiles(prev => {
      const next = [entry, ...prev.filter(f => f.name !== name)]
      saveFiles(next)
      return next
    })
  }

  const removeLocalFile = (name) => {
    setFiles(prev => {
      const next = prev.filter(f => f.name !== name)
      saveFiles(next)
      return next
    })
  }

  const handleFiles = useCallback(async (fileList) => {
    const allowed = ['md', 'txt']
    for (const file of fileList) {
      const ext = file.name.split('.').pop().toLowerCase()
      if (!allowed.includes(ext)) {
        setUploads(u => ({ ...u, [file.name]: 'error_type' }))
        continue
      }
      if (file.size > 10 * 1024 * 1024) {
        setUploads(u => ({ ...u, [file.name]: 'error_size' }))
        continue
      }

      setUploads(u => ({ ...u, [file.name]: 'uploading' }))
      try {
        const res = await uploadFile(file)
        if (res.code === 200) {
          setUploads(u => ({ ...u, [file.name]: 'done' }))
          addFile(file.name)
          await loadKnowledge(selectedFile)
        } else {
          setUploads(u => ({ ...u, [file.name]: 'error' }))
        }
      } catch {
        setUploads(u => ({ ...u, [file.name]: 'error' }))
      }
    }
  }, [loadKnowledge, selectedFile])

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const handleRebuild = async () => {
    setRebuilding(true)
    setMessage(null)
    try {
      const res = await rebuildIndex()
      if (res.code === 200) {
        setMessage({ ok: true, text: `索引重建完成，成功处理 ${res.data?.success_count ?? 0} 个文件。` })
        await loadKnowledge(selectedFile)
      } else {
        setMessage({ ok: false, text: '索引重建失败，请检查 uploads 目录和后端日志。' })
      }
    } catch {
      setMessage({ ok: false, text: '索引重建请求失败，请确认服务正在运行。' })
    } finally {
      setRebuilding(false)
    }
  }

  const handleSelectFile = async (filename) => {
    setSelectedFile(filename)
    setSelectedChunk(null)
    await loadKnowledge(filename)
  }

  const handleDelete = async (fileName) => {
    setMessage(null)
    try {
      const res = await deleteKnowledgeFile(fileName)
      if (res.code === 200) {
        removeLocalFile(fileName)
        if (selectedFile === fileName) setSelectedFile('')
        setSelectedChunk(null)
        setMessage({ ok: true, text: `已删除 ${res.data?.deleted ?? 0} 个知识库分片。` })
        await loadKnowledge(selectedFile === fileName ? '' : selectedFile)
      } else {
        setMessage({ ok: false, text: '删除失败，请稍后重试。' })
      }
    } catch {
      setMessage({ ok: false, text: '删除请求失败，请确认服务正在运行。' })
    }
  }

  return (
    <div className="h-screen max-h-screen overflow-y-auto bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 md:px-6 py-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-5">
          <div>
            <h1 className="text-xl font-semibold text-slate-800">知识库</h1>
            <p className="text-sm text-slate-500 mt-1">
              {stats.total_chunks || 0} 个分片，{indexedFiles.length} 个已索引文件
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => loadKnowledge(selectedFile)}
              disabled={loadingChunks}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={14} className={loadingChunks ? 'animate-spin' : ''} />
              刷新
            </button>
            <button
              onClick={handleRebuild}
              disabled={rebuilding}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={14} className={rebuilding ? 'animate-spin' : ''} />
              重建索引
            </button>
          </div>
        </div>

        {message && (
          <div className={`flex items-center gap-2 text-sm px-4 py-3 rounded-lg mb-4 ${
            message.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
          }`}>
            {message.ok ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
            {message.text}
          </div>
        )}

        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors mb-5 ${
            dragging ? 'border-brand-400 bg-brand-50' : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-white'
          }`}
        >
          <Upload size={30} className="mx-auto mb-3 text-slate-400" />
          <p className="text-sm font-medium text-slate-700">拖拽文件到此处，或点击选择文件</p>
          <p className="text-xs text-slate-400 mt-1.5">支持 .md 和 .txt，单个文件最大 10MB</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".md,.txt"
            className="hidden"
            onChange={e => handleFiles(e.target.files)}
          />
        </div>

        {Object.keys(uploads).length > 0 && (
          <div className="grid gap-2 md:grid-cols-2 mb-5">
            {Object.entries(uploads).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between bg-white rounded-lg border border-slate-200 px-4 py-2.5">
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={15} className="text-slate-400 shrink-0" />
                  <span className="text-sm text-slate-700 truncate">{name}</span>
                </div>
                <UploadStatus status={status} />
              </div>
            ))}
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <section className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700">文件</h2>
              <span className="text-xs text-slate-400">{indexedFiles.length || files.length}</span>
            </div>
            <div className="p-3">
              <button
                onClick={() => handleSelectFile('')}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  selectedFile === '' ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                <Layers size={15} />
                全部分片
              </button>
              <div className="mt-2 space-y-1">
                {(indexedFiles.length ? indexedFiles : files).map(file => {
                  const fileName = file.file_name || file.name
                  return (
                    <div
                      key={fileName}
                      className={`group flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedFile === fileName ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <button
                        onClick={() => handleSelectFile(fileName)}
                        className="flex flex-1 items-center gap-2 min-w-0 text-left"
                      >
                        <FileText size={15} className="shrink-0 opacity-70" />
                        <span className="truncate">{fileName}</span>
                        {file.chunk_count != null && (
                          <span className="ml-auto text-xs text-slate-400">{file.chunk_count}</span>
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(fileName)}
                        className="p-1 rounded-md text-slate-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                        title="删除知识库分片"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          </section>

          <section className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden min-h-[420px]">
            <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700">
                分片{selectedFile ? `：${selectedFile}` : ''}
              </h2>
              {loadingChunks && <Loader2 size={15} className="animate-spin text-brand-500" />}
            </div>

            {chunks.length === 0 && !loadingChunks ? (
              <div className="px-5 py-16 text-center text-sm text-slate-400">
                暂无分片。上传文件或重建索引后，这里会显示向量库中的实际内容。
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {chunks.map(chunk => (
                  <article key={chunk.id} className="px-5 py-4 hover:bg-slate-50 transition-colors">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                        <Layers size={15} className="text-brand-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-slate-800 truncate">{chunk.file_name}</p>
                            <p className="text-xs text-slate-400 mt-0.5 truncate">
                              {[chunk.h1, chunk.h2].filter(Boolean).join(' / ') || chunk.source}
                            </p>
                          </div>
                          <button
                            onClick={() => setSelectedChunk(chunk)}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md text-brand-600 hover:bg-brand-50 transition-colors shrink-0"
                          >
                            <Eye size={13} />
                            查看
                          </button>
                        </div>
                        <p className="text-sm text-slate-600 leading-relaxed mt-2 line-clamp-3 whitespace-pre-wrap">
                          {chunk.content_preview}
                        </p>
                        <p className="text-xs text-slate-400 mt-2">{chunk.char_count} 字符</p>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      {selectedChunk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[82vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-slate-800 truncate">{selectedChunk.file_name}</h3>
                <p className="text-xs text-slate-400 truncate">{selectedChunk.source}</p>
              </div>
              <button
                onClick={() => setSelectedChunk(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>
            <div className="overflow-y-auto p-5">
              <pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 font-sans">
                {selectedChunk.content}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function UploadStatus({ status }) {
  if (status === 'uploading') return (
    <span className="flex items-center gap-1 text-xs text-brand-500">
      <Loader2 size={13} className="animate-spin" /> 上传中
    </span>
  )
  if (status === 'done') return (
    <span className="flex items-center gap-1 text-xs text-emerald-600">
      <CheckCircle size={13} /> 成功
    </span>
  )
  if (status === 'error_type') return (
    <span className="flex items-center gap-1 text-xs text-red-500">
      <AlertCircle size={13} /> 格式不支持
    </span>
  )
  if (status === 'error_size') return (
    <span className="flex items-center gap-1 text-xs text-red-500">
      <AlertCircle size={13} /> 超过 10MB
    </span>
  )
  return (
    <span className="flex items-center gap-1 text-xs text-red-500">
      <AlertCircle size={13} /> 上传失败
    </span>
  )
}
