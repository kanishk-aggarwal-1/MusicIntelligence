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

export function SkeletonChartCard({ className = '' }) {
  return (
    <div className={`bg-zinc-900 rounded-xl border border-zinc-800 p-5 animate-pulse ${className}`}>
      <div className="h-4 bg-zinc-800 rounded w-28 mb-4" />
      <div className="h-40 bg-zinc-800 rounded" />
    </div>
  )
}
