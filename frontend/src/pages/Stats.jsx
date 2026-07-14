import { useEffect, useRef, useState } from 'react'
import { Activity, Database, Gauge, ListMusic, Radio, RefreshCw, Sparkles, Zap } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '../lib/api'

const POLL_MS = 60_000
const MAX_POINTS = 60 // up to one hour of visible-tab history

function StatCard({ icon: Icon, label, value, sub, accent = 'text-brand' }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-lg bg-brand/10 flex items-center justify-center">
          <Icon className={`w-4 h-4 ${accent}`} />
        </div>
        <span className="text-zinc-400 text-sm">{label}</span>
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-zinc-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function HitRateChart({ data }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-white font-semibold">Cache hit rate over time</h2>
        <span className="text-zinc-500 text-xs">updates every minute</span>
      </div>
      <div className="h-56">
        {data.length < 2 ? (
          <div className="h-full flex items-center justify-center text-zinc-600 text-sm">
            Collecting data points…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="t" tick={{ fill: '#71717a', fontSize: 11 }} stroke="#3f3f46" minTickGap={40} />
              <YAxis domain={[0, 100]} tick={{ fill: '#71717a', fontSize: 11 }} stroke="#3f3f46" unit="%" />
              <Tooltip
                contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8, color: '#fff' }}
                labelStyle={{ color: '#a1a1aa' }}
                formatter={(v) => [`${v}%`, 'Hit rate']}
              />
              <Line type="monotone" dataKey="rate" stroke="#1db954" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

export default function Stats() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const [live, setLive] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const d = await api.get('/stats')
        if (cancelled) return
        setStats(d)
        setError(null)
        setLive(true)
        const label = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        setHistory(prev => [...prev, { t: label, rate: d?.cache?.hit_rate_pct ?? 0 }].slice(-MAX_POINTS))
      } catch (e) {
        if (cancelled) return
        setError(e.message || 'Failed to load stats')
        setLive(false)
      }
    }

    poll()
    timerRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') poll()
    }, POLL_MS)
    return () => { cancelled = true; if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  const cache = stats?.cache || {}
  const ext = stats?.external_api_calls || {}
  const tracks = stats?.tracks || {}
  const playlists = stats?.playlists || {}

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <div className="max-w-5xl mx-auto p-4 md:p-8 space-y-6">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Activity className="w-6 h-6 text-brand" /> System Stats
            </h1>
            <p className="text-zinc-400 text-sm mt-1">
              Live, cumulative metrics from real traffic — persisted across restarts.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ${live ? 'bg-brand/10 text-brand' : 'bg-zinc-800 text-zinc-400'}`}>
              <span className={`w-2 h-2 rounded-full ${live ? 'bg-brand animate-pulse' : 'bg-zinc-500'}`} />
              {live ? 'Live' : 'Connecting…'}
            </span>
          </div>
        </header>

        {error && (
          <p className="text-red-400 text-sm bg-red-400/10 rounded-lg px-4 py-2.5">{error}</p>
        )}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Gauge} label="Cache hit rate" value={`${cache.hit_rate_pct ?? 0}%`} sub={`${cache.lookups ?? 0} lookups`} />
          <StatCard icon={Zap} label="API calls saved" value={`${cache.api_calls_saved_pct ?? 0}%`} sub={`${cache.api_calls_saved ?? 0} calls avoided`} />
          <StatCard icon={Database} label="Cache hits" value={(cache.hits ?? 0).toLocaleString()} sub={`${(cache.misses ?? 0).toLocaleString()} misses`} />
          <StatCard icon={Radio} label="External API calls" value={(ext.total ?? 0).toLocaleString()} sub={`Spotify ${ext.spotify ?? 0} · Last.fm ${ext.lastfm ?? 0}`} />
          <StatCard icon={RefreshCw} label="Tracks synced" value={(tracks.synced ?? 0).toLocaleString()} />
          <StatCard icon={Sparkles} label="Tracks enriched" value={(tracks.enriched ?? 0).toLocaleString()} />
          <StatCard icon={ListMusic} label="Playlists generated" value={(playlists.generated ?? 0).toLocaleString()} />
          <StatCard icon={Gauge} label="Playlist resolution" value={`${playlists.resolution_rate_pct ?? 0}%`} sub={`${playlists.tracks_resolved ?? 0}/${playlists.tracks_requested ?? 0} URIs`} />
        </div>

        <HitRateChart data={history} />

        <p className="text-zinc-600 text-xs text-center">
          {stats?.note} {stats?.updated_at && `· Last updated ${new Date(stats.updated_at).toLocaleString()}`}
        </p>
      </div>
    </div>
  )
}
