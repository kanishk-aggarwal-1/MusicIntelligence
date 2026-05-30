import { useState, useEffect } from 'react'
import { RefreshCw, Trash2, BarChart2, Music, Play, Pause, Target, CheckCircle, X } from 'lucide-react'
import { api } from '../lib/api'
import { usePlayer } from '../contexts/PlayerContext'
import Spinner from '../components/ui/Spinner'
import ErrorBoundary from '../components/ui/ErrorBoundary'

function Section({ title, description, children }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800 space-y-4">
      <div>
        <h2 className="text-white font-semibold">{title}</h2>
        {description && <p className="text-zinc-400 text-sm mt-1">{description}</p>}
      </div>
      {children}
    </div>
  )
}

function Result({ data }) {
  if (!data) return null
  return (
    <pre className="text-xs bg-zinc-950 rounded-lg p-3 text-zinc-300 overflow-auto max-h-48">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function ActionButton({ onClick, loading, icon: Icon, label, variant = 'default' }) {
  const base = 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60'
  const variants = {
    default:  'bg-zinc-800 text-white hover:bg-zinc-700',
    primary:  'bg-brand text-black hover:bg-green-400',
    danger:   'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20',
  }
  return (
    <button onClick={onClick} disabled={loading} className={`${base} ${variants[variant]}`}>
      {loading ? <Spinner size="sm" /> : <Icon className="w-4 h-4" />}
      {label}
    </button>
  )
}

function DiscoveryFeed() {
  const [items, setItems]   = useState([])
  const [loading, setLoading] = useState(true)
  const { play, isPlaying } = usePlayer()

  useEffect(() => {
    api.get('/insights/discovery-feed', { limit: 20 })
      .then(d => setItems(d.items || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex justify-center py-6"><Spinner /></div>
  if (!items.length) return <p className="text-zinc-500 text-sm">Sync and enrich your library to generate recommendations.</p>

  return (
    <div className="space-y-1">
      {items.map((item, i) => {
        const song = { ...item, id: item.song_id }
        const active = isPlaying(song)
        return (
          <div key={item.song_id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-800 group">
            <span className="w-5 text-xs text-zinc-600 text-center shrink-0">{i + 1}</span>
            <div className="relative w-10 h-10 shrink-0">
              {item.image_url
                ? <img src={item.image_url} alt="" className="w-full h-full rounded object-cover" />
                : <div className="w-full h-full rounded bg-zinc-800 flex items-center justify-center"><Music className="w-4 h-4 text-zinc-600" /></div>}
              {item.preview_url && (
                <button
                  onClick={() => play(song)}
                  className="absolute inset-0 rounded bg-black/60 items-center justify-center hidden group-hover:flex"
                >
                  {active ? <Pause className="w-3 h-3 text-brand" /> : <Play className="w-3 h-3 text-white" />}
                </button>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm truncate">{item.title}</p>
              <p className="text-zinc-500 text-xs truncate">{item.artist}</p>
              {item.reasons?.[0] && (
                <p className="text-zinc-600 text-xs italic truncate mt-0.5">{item.reasons[0]}</p>
              )}
            </div>
            <span className="text-xs text-zinc-600 shrink-0">{item.score?.toFixed(2)}</span>
          </div>
        )
      })}
    </div>
  )
}

const GOAL_TYPES = [
  { value: 'new_songs_per_week',      label: 'New songs per week'      },
  { value: 'listening_days_per_week', label: 'Active days per week'    },
  { value: 'repeat_rate_max',         label: 'Max repeat rate (%)'     },
]

function GoalsSection() {
  const [goals, setGoals]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [creating, setCreating] = useState(false)
  const [form, setForm]         = useState({ goal_type: 'new_songs_per_week', target_value: 5, period: 'weekly' })
  const [toast, setToast]       = useState(null)

  function loadGoals() {
    setLoading(true)
    api.get('/insights/goals-status')
      .then(d => setGoals(d.goals || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadGoals() }, [])

  async function createGoal() {
    setCreating(true)
    try {
      await api.post('/insights/goals', { ...form, target_value: Number(form.target_value) })
      loadGoals()
    } catch (e) { console.error(e) }
    finally { setCreating(false) }
  }

  async function removeGoal(goalId) {
    try {
      await api.delete(`/insights/goals/${goalId}`)
      setGoals(prev => prev.filter(g => g.goal_id !== goalId))
      setToast('Goal removed')
      setTimeout(() => setToast(null), 2000)
    } catch (e) { console.error(e) }
  }

  return (
    <div className="space-y-4">
      {toast && (
        <div className="rounded-lg bg-brand/10 border border-brand/20 text-brand text-sm px-3 py-2">
          {toast}
        </div>
      )}
      {/* Create form */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-xs text-zinc-500">Goal type</label>
          <select
            value={form.goal_type}
            onChange={e => setForm(f => ({ ...f, goal_type: e.target.value }))}
            className="bg-zinc-800 border border-zinc-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-brand"
          >
            {GOAL_TYPES.map(g => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-500">Target</label>
          <input
            type="number" min={1} max={100}
            value={form.target_value}
            onChange={e => setForm(f => ({ ...f, target_value: e.target.value }))}
            className="w-20 bg-zinc-800 border border-zinc-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-brand"
          />
        </div>
        <button
          onClick={createGoal}
          disabled={creating}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-brand text-black hover:bg-green-400 disabled:opacity-50"
        >
          {creating ? <Spinner size="sm" /> : <Target className="w-4 h-4" />}
          Add Goal
        </button>
      </div>

      {/* Active goals */}
      {loading ? <Spinner /> : goals.length === 0 ? (
        <p className="text-zinc-500 text-sm">No active goals yet.</p>
      ) : (
        <div className="space-y-3">
          {goals.map(g => {
            const pct = Math.min(100, Math.round((g.progress / g.target) * 100))
            const onTrack = g.status === 'on_track'
            return (
              <div key={g.goal_id} className="bg-zinc-950 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-white text-sm">{GOAL_TYPES.find(t => t.value === g.goal_type)?.label ?? g.goal_type}</p>
                  <div className="flex items-center gap-1.5">
                    {onTrack && <CheckCircle className="w-3.5 h-3.5 text-green-400" />}
                    <span className={`text-xs font-medium ${onTrack ? 'text-green-400' : 'text-yellow-400'}`}>
                      {g.progress} / {g.target}
                    </span>
                    <button
                      type="button"
                      title="Remove goal"
                      onClick={() => removeGoal(g.goal_id)}
                      className="w-5 h-5 rounded flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-zinc-800"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${onTrack ? 'bg-green-400' : 'bg-brand'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Features() {
  const [backfillResult, setBackfillResult] = useState(null)
  const [backfillLoading, setBackfillLoading] = useState(false)
  const [retryFailed, setRetryFailed] = useState(false)
  const [retryPartial, setRetryPartial] = useState(false)

  const [qualityResult, setQualityResult] = useState(null)
  const [qualityLoading, setQualityLoading] = useState(false)

  const [dedupPreview, setDedupPreview] = useState(null)
  const [dedupLoading, setDedupLoading] = useState(false)
  const [dedupApplying, setDedupApplying] = useState(false)
  const [dedupResult, setDedupResult] = useState(null)

  const [cacheClearing, setCacheClearing] = useState(false)
  const [cacheResult, setCacheResult] = useState(null)

  async function handleBackfill() {
    setBackfillLoading(true)
    try {
      const job = await api.post(`/user/backfill-metadata/job?limit=500&retry_partial=${retryPartial}&retry_failed=${retryFailed}`)
      setBackfillResult(job)
    } catch (e) {
      setBackfillResult({ error: e.message })
    } finally {
      setBackfillLoading(false)
    }
  }

  async function handleQuality() {
    setQualityLoading(true)
    try {
      const res = await api.get('/insights/data-quality')
      setQualityResult(res)
    } catch (e) {
      setQualityResult({ error: e.message })
    } finally {
      setQualityLoading(false)
    }
  }

  async function handleDedupPreview() {
    setDedupLoading(true)
    try {
      const res = await api.get('/insights/dedup-preview')
      setDedupPreview(res)
    } catch (e) {
      setDedupPreview({ error: e.message })
    } finally {
      setDedupLoading(false)
    }
  }

  async function handleDedupApply() {
    setDedupApplying(true)
    try {
      const res = await api.post('/insights/dedup-apply')
      setDedupResult(res)
      setDedupPreview(null)
    } catch (e) {
      setDedupResult({ error: e.message })
    } finally {
      setDedupApplying(false)
    }
  }

  async function handleClearCache() {
    setCacheClearing(true)
    try {
      const res = await api.post('/insights/cache/clear?provider=lastfm')
      setCacheResult(res)
    } catch (e) {
      setCacheResult({ error: e.message })
    } finally {
      setCacheClearing(false)
    }
  }

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Features</h1>
        <p className="text-zinc-400 text-sm mt-1">Maintenance and advanced tools</p>
      </div>

      <Section title="For You" description="Songs from your library ranked by your current taste profile.">
        <ErrorBoundary><DiscoveryFeed /></ErrorBoundary>
      </Section>

      <Section title="Listening Goals" description="Set weekly targets and track your progress.">
        <ErrorBoundary><GoalsSection /></ErrorBoundary>
      </Section>

      <Section title="Metadata Enrichment" description="Fetch Last.fm tags and genre data for songs in your library.">
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input type="checkbox" checked={retryPartial} onChange={e => setRetryPartial(e.target.checked)} className="accent-brand" />
            Retry partial
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input type="checkbox" checked={retryFailed} onChange={e => setRetryFailed(e.target.checked)} className="accent-brand" />
            Retry failed
          </label>
          <ActionButton onClick={handleBackfill} loading={backfillLoading} icon={RefreshCw} label="Run Backfill" variant="primary" />
        </div>
        <Result data={backfillResult} />
      </Section>

      <Section title="Data Quality" description="Check enrichment coverage across your library.">
        <ActionButton onClick={handleQuality} loading={qualityLoading} icon={BarChart2} label="Check Coverage" />
        {qualityResult && !qualityResult.error && (
          <div className="grid grid-cols-2 gap-3">
            {(qualityResult.coverage || []).map(c => (
              <div key={c.metric} className="bg-zinc-950 rounded-lg p-3">
                <p className="text-xs text-zinc-500">{c.metric}</p>
                <p className="text-white font-semibold">{c.percent}%</p>
                <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-brand rounded-full" style={{ width: `${c.percent}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
        {qualityResult?.error && <p className="text-red-400 text-sm">{qualityResult.error}</p>}
      </Section>

      <Section title="Deduplication" description="Find and merge duplicate songs in your library.">
        <div className="flex gap-2 flex-wrap">
          <ActionButton onClick={handleDedupPreview} loading={dedupLoading} icon={BarChart2} label="Preview Duplicates" />
          {dedupPreview?.duplicate_groups?.length > 0 && (
            <ActionButton onClick={handleDedupApply} loading={dedupApplying} icon={Trash2} label={`Merge ${dedupPreview.duplicate_groups.length} groups`} variant="danger" />
          )}
        </div>
        {dedupPreview && !dedupPreview.error && (
          <p className="text-zinc-400 text-sm">Found {dedupPreview.duplicate_groups?.length ?? 0} duplicate groups</p>
        )}
        <Result data={dedupResult} />
      </Section>

      <Section title="Cache" description="Clear the Last.fm API response cache to force fresh enrichment.">
        <ActionButton onClick={handleClearCache} loading={cacheClearing} icon={Trash2} label="Clear Last.fm Cache" variant="danger" />
        <Result data={cacheResult} />
      </Section>
    </div>
  )
}
