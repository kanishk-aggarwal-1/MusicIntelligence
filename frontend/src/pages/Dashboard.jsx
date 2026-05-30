import { useCallback, useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, CartesianGrid,
  LineChart, Line, Legend,
} from 'recharts'
import { Music2, Users, Disc, TrendingUp, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import Spinner from '../components/ui/Spinner'
import ErrorBoundary from '../components/ui/ErrorBoundary'
import { useSyncFlow } from '../hooks/useSyncFlow'

function formatMonth(str) {
  if (!str) return ''
  const d = new Date(str)
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
}

function pivotTimeline(rows, key) {
  const byMonth = {}
  const allKeys = new Set()
  for (const row of rows) {
    const m = formatMonth(row.month)
    if (!byMonth[m]) byMonth[m] = { month: m }
    byMonth[m][row[key]] = (byMonth[m][row[key]] || 0) + row.plays
    allKeys.add(row[key])
  }
  return { data: Object.values(byMonth), keys: [...allKeys].slice(0, 5) }
}

const COLORS = ['#1db954', '#17a348', '#138d3c', '#0f7030', '#0b5c26']

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

function ChartCard({ title, children, empty = 'No data yet', hasData = true, className = '' }) {
  return (
    <ErrorBoundary>
      <div className={`bg-zinc-900 rounded-xl p-5 border border-zinc-800 ${className}`}>
        <h2 className="text-white font-semibold mb-4">{title}</h2>
        {hasData ? children : <p className="text-zinc-500 text-sm">{empty}</p>}
      </div>
    </ErrorBoundary>
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

  const { syncing, syncJob, enrichmentJob, startSync } = useSyncFlow({
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

  useEffect(() => {
    loadData()
  }, [loadData])

  if (loading) return (
    <div className="flex items-center justify-center h-96">
      <Spinner size="lg" />
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
            <button
              type="button"
              onClick={startSync}
              disabled={syncing}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-brand text-black text-sm font-semibold hover:bg-green-400 disabled:opacity-60"
            >
              {syncing || syncJob ? <Spinner size="sm" /> : <RefreshCw className="w-4 h-4" />}
              {syncing || syncJob ? 'Syncing...' : 'Sync Now'}
            </button>
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ChartCard title="Top Artists" hasData={topArtists.length > 0} className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={topArtists} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="artist_name" tick={{ fill: '#a1a1aa', fontSize: 11 }} width={90} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
              <Bar dataKey="play_count" fill="#1db954" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Top Genres" hasData={topGenres.length > 0} empty="No genre data yet">
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={topGenres} dataKey="play_count" nameKey="genre" cx="50%" cy="50%" outerRadius={70} strokeWidth={0}>
                {topGenres.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">
            {topGenres.map((g, i) => (
              <div key={g.genre} className="flex items-center gap-2 text-xs">
                <div className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                <span className="text-zinc-300 truncate flex-1">{g.genre}</span>
                <span className="text-zinc-500">{g.play_count}</span>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Plays by Hour" hasData={hourly.length > 0}>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={hourly}>
              <defs>
                <linearGradient id="hourGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1db954" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#1db954" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="hour" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
              <Area type="monotone" dataKey="play_count" stroke="#1db954" fill="url(#hourGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Plays by Day" hasData={daily.length > 0}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={daily}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="day" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
              <Bar dataKey="play_count" fill="#1db954" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {timeline && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {(() => {
            const { data, keys } = pivotTimeline(timeline.monthly_top_genres || [], 'genre')
            return (
              <ChartCard title="Genre Timeline" hasData={data.length > 0} empty="Not enough history yet">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="month" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#a1a1aa' }} />
                    {keys.map((k, i) => (
                      <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            )
          })()}
          {(() => {
            const { data, keys } = pivotTimeline(timeline.monthly_top_artists || [], 'artist')
            return (
              <ChartCard title="Artist Timeline" hasData={data.length > 0} empty="Not enough history yet">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="month" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#a1a1aa' }} />
                    {keys.map((k, i) => (
                      <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            )
          })()}
        </div>
      )}
    </div>
  )
}
