export default function StatusBadge({ ok, label }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
      ok
        ? 'bg-emerald-50 text-emerald-700'
        : 'bg-red-50 text-red-600'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-500'}`} />
      {label ?? (ok ? '正常' : '异常')}
    </span>
  )
}
