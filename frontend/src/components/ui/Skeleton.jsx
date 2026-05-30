export function SkeletonLine({ className = '' }) {
  return <div className={`bg-zinc-800 rounded animate-pulse ${className}`} />
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`bg-zinc-900 rounded-xl border border-zinc-800 p-5 space-y-3 animate-pulse ${className}`}>
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-zinc-800" />
        <div className="h-3 bg-zinc-800 rounded w-24" />
      </div>
      <div className="h-7 bg-zinc-800 rounded w-16" />
      <div className="h-3 bg-zinc-800 rounded w-32" />
    </div>
  )
}

export function SkeletonRow({ className = '' }) {
  return (
    <div className={`flex items-center gap-3 px-3 py-2 animate-pulse ${className}`}>
      <div className="w-7 h-3 bg-zinc-800 rounded" />
      <div className="w-10 h-10 rounded bg-zinc-800 shrink-0" />
      <div className="flex-1 space-y-1.5 min-w-0">
        <div className="h-3 bg-zinc-800 rounded w-3/5" />
        <div className="h-2.5 bg-zinc-800 rounded w-2/5" />
      </div>
    </div>
  )
}

export function SkeletonChartCard({ className = '' }) {
  return (
    <div className={`bg-zinc-900 rounded-xl border border-zinc-800 p-5 animate-pulse ${className}`}>
      <div className="h-4 bg-zinc-800 rounded w-28 mb-4" />
      <div className="h-40 bg-zinc-800 rounded" />
    </div>
  )
}
