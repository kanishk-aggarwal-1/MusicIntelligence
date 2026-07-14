import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Music2, Users, Disc, TrendingUp, RefreshCw, Upload, ArrowRight, Heart, ListMusic, Tags, CheckCircle, Circle, Clock3, FastForward } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import Spinner from '../components/ui/Spinner'
import { SkeletonCard, SkeletonChartCard } from '../components/ui/Skeleton'
import { useSyncFlow } from '../hooks/useSyncFlow'
import { useAuth } from '../contexts/AuthContext'

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
  const navigate = useNavigate()
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [days, setDays] = useState(30)
  const [enriching, setEnriching] = useState(false)
  const [onboarding, setOnboarding] = useState(null)

  const loadOnboarding = useCallback(() => {
    if (user?.is_demo) return
    api.get('/user/onboarding-status').then(setOnboarding).catch(() => {})
  }, [user?.is_demo])

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
      loadOnboarding()
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
    loadOnboarding()
  }, [loadData, loadOnboarding])

  const trend = useMemo(() => computeTrend(timeline), [timeline])

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
              <div className="border-t border-zinc-800 pt-4 space-y-2">
                <p className="text-xs text-zinc-500">
                  Spotify limits live sync to your last 50 tracks.{' '}
                  <strong className="text-zinc-400">Import years of history at once:</strong>
                </p>
                <button
                  type="button"
                  onClick={() => navigate('/features')}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 text-zinc-300 text-sm hover:bg-zinc-700 transition-colors"
                >
                  <Upload className="w-4 h-4" />
                  Import Spotify Data Export
                </button>
              </div>
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

      {user?.is_demo && (
        <section className="rounded-xl border border-brand/20 bg-brand/5 p-5 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-brand">Guided demo</p>
            <h2 className="mt-1 text-lg font-semibold text-white">See how listening history becomes useful recommendations</h2>
            <p className="mt-1 text-sm text-zinc-400">The data below is a seeded example. These three stops show the main product workflow.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              { to: '/browse', icon: Tags, title: '1. Explore taste', text: 'Browse the genres and tags extracted from listening history.' },
              { to: '/for-you', icon: Heart, title: '2. See recommendations', text: 'Inspect personalized picks and the reasons behind them.' },
              { to: '/playlists', icon: ListMusic, title: '3. Build a playlist', text: 'Generate a safe preview with familiarity and diversity controls.' },
            ].map(({ to, icon: Icon, title, text }) => (
              <button key={to} type="button" onClick={() => navigate(to)} className="group rounded-lg border border-zinc-800 bg-zinc-900 p-4 text-left hover:border-brand/40">
                <Icon className="h-4 w-4 text-brand" />
                <p className="mt-3 text-sm font-medium text-white">{title}</p>
                <p className="mt-1 text-xs leading-relaxed text-zinc-500">{text}</p>
                <span className="mt-3 inline-flex items-center gap-1 text-xs text-brand">Open <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" /></span>
              </button>
            ))}
          </div>
        </section>
      )}

      {!user?.is_demo && onboarding && !onboarding.complete && (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-brand">Getting started</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Finish setting up your music intelligence</h2>
            <p className="mt-1 text-sm text-zinc-400">Your progress is saved. You can leave and continue later.</p>
          </div>
          <div className="space-y-2">
            {[
              { key: 'spotify_connected', label: 'Connect Spotify', action: null },
              { key: 'history_synced', label: 'Sync recent listening history', action: handleSync },
              { key: 'metadata_ready', label: 'Enrich songs with tags and genres', action: () => navigate('/features') },
              { key: 'playlist_previewed', label: 'Generate your first playlist preview', action: () => navigate('/playlists') },
              { key: 'playlist_saved', label: 'Save a playlist to Spotify', action: () => navigate('/playlists') },
            ].map(step => {
              const done = onboarding.steps?.[step.key]
              return (
                <div key={step.key} className="flex items-center gap-3 rounded-lg bg-zinc-950 px-3 py-2.5">
                  {done ? <CheckCircle className="h-4 w-4 shrink-0 text-brand" /> : <Circle className="h-4 w-4 shrink-0 text-zinc-600" />}
                  <span className={`flex-1 text-sm ${done ? 'text-zinc-500 line-through' : 'text-zinc-200'}`}>{step.label}</span>
                  {!done && step.action && (
                    <button type="button" onClick={step.action} className="text-xs font-medium text-brand hover:text-green-300">Start</button>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard icon={TrendingUp} label="Total plays" value={totalPlays.toLocaleString()} />
        <StatCard icon={Clock3} label="Minutes listened" value={(stats?.minutes_listened ?? 0).toLocaleString()} sub="from detailed history" />
        <StatCard icon={FastForward} label="Skip rate" value={stats?.skip_rate_percent == null ? '-' : `${stats.skip_rate_percent}%`} sub="when skip data is available" />
        <StatCard icon={Users} label="Top artist" value={topArtist} />
        <StatCard icon={Disc} label="Top genre" value={topGenre} />
        <StatCard icon={Music2} label="Artists" value={(stats?.total_artists ?? topArtists.length).toLocaleString()} sub="distinct artists" />
      </div>

      {trend && (
        <p className="text-zinc-400 text-sm italic border-l-2 border-brand/40 pl-3">{trend}</p>
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
