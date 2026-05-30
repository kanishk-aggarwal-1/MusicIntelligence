import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Music2, Users, Disc, TrendingUp, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import Spinner from '../components/ui/Spinner'
import { SkeletonCard, SkeletonChartCard } from '../components/ui/Skeleton'
import { useSyncFlow } from '../hooks/useSyncFlow'

/** Derive a one-sentence trend from the taste-timeline payload. */
function computeTrend(timeline) {
  const rows = timeline?.monthly_top_genres || []
  const months = [...new Set(rows.map(r => r.month))].sort()
  if (months.length < 2) return null

  const cur = months[months.length - 1]
  const prev = months[months.length - 2]

  const tally = (m) => {
    const t = {}; let total = 0
    for (const r of rows) {
      if (r.month !== m) continue
      t[r.genre] = (t[r.genre] || 0) + r.plays
      total += r.plays
    }
    return { t, total }
  }

  const { t: curT, total: curTotal } = tally(cur)
  const { t: prevT, total: prevTotal } = tally(prev)
  if (!curTotal || !prevTotal) return null

  const [topGenre] = Object.entries(curT).sort((a, b) => b[1] - a[1])
  if (!topGenre) return null

  const [genre] = topGenre
  const curPct  = (curT[genre]  || 0) / curTotal
  const prevPct = (prevT[genre] || 0) / prevTotal
  const diff = curPct - prevPct

  if (Math.abs(diff) < 0.05) return `Your listening is steady — ${genre} leads this month.`
  const dir = diff > 0 ? 'more' : 'less'
  const change = Math.round(Math.abs(diff) * 100)
  return `You've been listening to ${dir} ${genre} this month (${diff > 0 ? '+' : '-'}${change}% of plays).`
}

const DashboardCharts = lazy(() => import('../components/dashboard/DashboardCharts'))

function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-lg bg-brand/10 flex items-center justify-center">
          <Icon className="w-4 h-4 text-brand" />
        </div>
        <span className="text-zinc-400 text-sm">{label}</span>
      </div>
      <p className="text-2xl font-bold text-white truncate">{value ?? '-'}</p>
      {sub && <p className="text-zinc-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [days, setDays] = useState(30)
  const [enriching, setEnriching] = useState(false)

  const loadData = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      api.get('/dashboard/stats', { days }),
      api.get('/insights/taste-timeline', { months: 6 }),
    ])
      .then(([s, t]) => { setStats(s); setTimeline(t) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [days])

  const { syncing, syncJob, enrichmentJob, syncError, startSync } = useSyncFlow({
    onSyncFinished: (job) => {
      const result = job.result || {}
      if (result.enrichment_queued) setEnriching(true)
      else loadData()
    },
    onEnrichmentFinished: () => {
      setEnriching(false)
      loadData()
    },
  })

  async function handleSync() {
    try { await startSync() } catch { /* error shown via syncError */ }
  }

  useEffect(() => {
    loadData()
  }, [loadData])

  if (loading) return (
    <div className="p-4 md:p-8 space-y-8">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <SkeletonChartCard className="lg:col-span-2" />
        <SkeletonChartCard />
      </div>
    </div>
  )
  if (error) return <div className="p-8 text-red-400">{error}</div>

  const topArtists = (stats?.top_artists || []).map(a => ({
    ...a,
    artist_name: a.artist_name || a.artist,
    play_count: a.play_count ?? a.plays,
  })).slice(0, 10)
  const topGenres = (stats?.top_genres || []).map(g => ({ ...g, play_count: g.play_count ?? g.plays })).slice(0, 6)
  const hourly = (stats?.hourly_listening || []).map(h => ({ hour: h.hour, play_count: h.play_count ?? h.plays }))
  const daily = (stats?.daily_listening || []).map(d => ({ day: d.day, play_count: d.play_count ?? d.plays }))

  const totalPlays = stats?.total_plays ?? topArtists.reduce((s, a) => s + (a.play_count || 0), 0)
  const topArtist = topArtists[0]?.artist_name ?? '-'
  const topGenre = topGenres[0]?.genre ?? '-'

  if (totalPlays === 0) {
    return (
      <div className="p-8 min-h-[calc(100vh-3.5rem)] md:min-h-screen flex items-center justify-center">
        <div className="w-full max-w-md bg-zinc-900 rounded-xl border border-zinc-800 p-6 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-brand/10 text-brand flex items-center justify-center mx-auto">
            <Music2 className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white">Welcome - sync your Spotify history to get started.</h1>
            <p className="text-sm text-zinc-400 mt-2">
              {enriching || enrichmentJob
                ? 'Enriching tags and genres... this takes a few minutes'
                : 'Your dashboard will fill in as soon as your listening history lands.'}
            </p>
          </div>
          {enriching || enrichmentJob ? (
            <div className="flex items-center justify-center gap-2 text-zinc-400 text-sm">
              <Spinner size="sm" />
              <span>{enrichmentJob?.message || 'Enriching tags and genres...'}</span>
            </div>
          ) : (
            <>
              {syncError && (
                <p className="text-red-400 text-sm bg-red-400/10 rounded-lg px-3 py-2">{syncError}</p>
              )}
              <button
                type="button"
                onClick={handleSync}
                disabled={syncing}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-brand text-black text-sm font-semibold hover:bg-green-400 disabled:opacity-60"
              >
                {syncing || syncJob ? <Spinner size="sm" /> : <RefreshCw className="w-4 h-4" />}
                {syncing || syncJob ? 'Syncing...' : 'Sync Now'}
              </button>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-8 space-y-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-zinc-400 text-sm mt-1">Your listening at a glance</p>
        </div>
        <select
          value={days}
          onChange={e => setDays(Number(e.target.value))}
          className="bg-zinc-800 border border-zinc-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-brand"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={TrendingUp} label="Total plays" value={totalPlays.toLocaleString()} />
        <StatCard icon={Users} label="Top artist" value={topArtist} />
        <StatCard icon={Disc} label="Top genre" value={topGenre} />
        <StatCard icon={Music2} label="Artists" value={topArtists.length} />
      </div>

      {computeTrend(timeline) && (
        <p className="text-zinc-400 text-sm italic border-l-2 border-brand/40 pl-3">
          {computeTrend(timeline)}
        </p>
      )}

      <Suspense fallback={<div className="flex items-center justify-center py-12"><Spinner /></div>}>
        <DashboardCharts
          topArtists={topArtists}
          topGenres={topGenres}
          hourly={hourly}
          daily={daily}
          timeline={timeline}
        />
      </Suspense>
    </div>
  )
}
