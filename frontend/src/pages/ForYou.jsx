import { useState, useEffect } from 'react'
import { ExternalLink, Music, Pause, Play, Target, CheckCircle, X, RefreshCw, Sparkles, Heart } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
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

const SETUP_STEPS = [
  { icon: RefreshCw,  label: 'Sync your history',   desc: 'Go to Dashboard and click Sync Now.',     path: '/dashboard' },
  { icon: Sparkles,   label: 'Enrich your library',  desc: 'Go to Tools → Run Backfill to fetch tags.', path: '/features' },
  { icon: Heart,      label: 'Come back here',        desc: 'Recommendations appear once enrichment finishes.', path: null },
]

function DiscoveryEmptyState() {
  const navigate = useNavigate()
  return (
    <div className="space-y-4">
      <p className="text-zinc-400 text-sm">
        Recommendations need your listening history and enriched tags. Complete these steps:
      </p>
      <ol className="space-y-3">
        {SETUP_STEPS.map(({ icon: Icon, label, desc, path }, i) => (
          <li key={i} className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 mt-0.5">
              <span className="text-xs text-zinc-400 font-semibold">{i + 1}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium">{label}</p>
              <p className="text-zinc-500 text-xs mt-0.5">{desc}</p>
            </div>
            {path && (
              <button
                onClick={() => navigate(path)}
                className="shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
              >
                <Icon className="w-3 h-3" /> Go
              </button>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

function TasteProfileSkeleton() {
  return (
    <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800 space-y-3">
      <div className="h-4 w-40 bg-zinc-800 rounded animate-pulse" />
      <div className="flex gap-2">
        {[0, 1, 2, 3].map(i => <div key={i} className="h-6 w-20 bg-zinc-800 rounded-full animate-pulse" />)}
      </div>
    </div>
  )
}

function TasteProfileSummary() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/insights/taste-profile')
      .then(d => setProfile(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <TasteProfileSkeleton />
  if (!profile) return null

  const strength = profile.profile_strength || 'building'
  const label = `${strength.charAt(0).toUpperCase()}${strength.slice(1)} taste profile`

  return (
    <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-zinc-300 text-sm">
          {label} <span className="text-zinc-600">·</span> {profile.total_tagged_songs || 0} tagged songs
        </p>
        {strength === 'building' && (
          <p className="text-zinc-500 text-xs">Keep syncing and enriching to improve recommendations.</p>
        )}
      </div>
      {!!profile.top_tags?.length && (
        <div className="flex flex-wrap gap-2">
          {profile.top_tags.slice(0, 4).map(tag => (
            <span key={tag.name} className="px-2.5 py-1 rounded-full bg-brand/10 text-brand text-xs">
              {tag.name} {tag.pct}%
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function DiscoverSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {[0, 1, 2, 3].map(i => (
        <div key={i} className="bg-zinc-950 rounded-lg p-3 space-y-2">
          <div className="h-4 w-2/3 bg-zinc-800 rounded animate-pulse" />
          <div className="h-3 w-1/2 bg-zinc-800 rounded animate-pulse" />
          <div className="h-5 w-24 bg-zinc-800 rounded-full animate-pulse" />
        </div>
      ))}
    </div>
  )
}

function DiscoverSection() {
  const [items, setItems] = useState([])
  const [artistCount, setArtistCount] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    let timer = null
    // Cap polling so a job that never finishes (e.g. a dropped background task)
    // can't poll forever — ~30s of attempts, then give up gracefully.
    const MAX_POLLS = 20
    let polls = 0

    async function load() {
      try {
        const d = await api.get('/insights/new-for-you')
        if (cancelled) return
        setArtistCount(d.distinct_artist_count)

        // Discovery now runs in a background job. On a cache miss the endpoint
        // returns status:"pending" + a job id; poll it, then refetch the
        // now-cached results. Cached/instant answers return status:"ready".
        if (d.status === 'pending' && d.job_id) {
          timer = setInterval(async () => {
            polls += 1
            if (polls > MAX_POLLS) {
              clearInterval(timer)
              if (!cancelled) setLoading(false)
              return
            }
            try {
              const job = await api.get(`/jobs/${d.job_id}`)
              if (cancelled) return
              if (['succeeded', 'failed', 'cancelled'].includes(job.status)) {
                clearInterval(timer)
                const fresh = await api.get('/insights/new-for-you')
                if (cancelled) return
                setItems(fresh.items || [])
                setArtistCount(fresh.distinct_artist_count)
                setLoading(false)
              }
            } catch {
              clearInterval(timer)
              if (!cancelled) setLoading(false)
            }
          }, 1500)
        } else {
          setItems(d.items || [])
          setLoading(false)
        }
      } catch {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true; if (timer) clearInterval(timer) }
  }, [])

  if (loading) return <DiscoverSkeleton />
  if (!items.length) {
    return (
      <p className="text-zinc-500 text-sm">
        {artistCount != null && artistCount < 5
          ? 'Listen to more music to unlock discoveries'
          : 'No new discoveries right now.'}
      </p>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {items.slice(0, 10).map((item, i) => (
        <div key={`${item.title}-${item.artist}-${i}`} className="bg-zinc-950 rounded-lg p-3 border border-zinc-900 hover:border-zinc-800 transition-colors">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-white text-sm font-medium truncate">{item.title}</p>
              <p className="text-zinc-500 text-xs truncate mt-0.5">{item.artist}</p>
            </div>
            {item.spotify_url && (
              <a
                href={item.spotify_url}
                target="_blank"
                rel="noreferrer"
                title="Open in Spotify"
                className="shrink-0 w-7 h-7 rounded-lg bg-zinc-900 text-zinc-400 hover:text-brand hover:bg-zinc-800 flex items-center justify-center"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          {item.reason && (
            <span className="inline-flex mt-3 px-2 py-0.5 rounded-full bg-zinc-900 text-zinc-500 text-xs">
              {item.reason}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function matchLabel(score) {
  if (score == null) return null
  if (score >= 0.8) return { text: 'Strong match', color: 'text-green-400' }
  if (score >= 0.5) return { text: 'Good match',   color: 'text-brand'     }
  return               { text: 'Possible match', color: 'text-zinc-500'   }
}

function DiscoveryFeed() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const { play, isPlaying } = usePlayer()

  useEffect(() => {
    api.get('/insights/discovery-feed', { limit: 20 })
      .then(d => setItems(d.items || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex justify-center py-6"><Spinner /></div>
  if (!items.length) return <DiscoveryEmptyState />

  return (
    <div className="space-y-1">
      {items.map((item, i) => {
        const song = { ...item, id: item.song_id }
        const active = isPlaying(song)
        const match = matchLabel(item.score)
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
              {item.reasons?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {item.reasons.slice(0, 3).map(reason => (
                    <span key={reason} className="text-zinc-500 text-[10px] bg-zinc-800/60 rounded px-1.5 py-0.5 first-letter:capitalize">
                      {reason}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {match && (
              <span className={`text-xs shrink-0 hidden sm:inline ${match.color}`}>{match.text}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

const GOAL_TYPES = [
  { value: 'new_songs_per_week',      label: 'New songs per week'   },
  { value: 'listening_days_per_week', label: 'Active days per week' },
  { value: 'repeat_rate_max',         label: 'Max repeat rate (%)'  },
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

export default function ForYou() {
  return (
    <div className="p-4 md:p-8 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">For You</h1>
        <p className="text-zinc-400 text-sm mt-1">Recommendations and goals based on your taste profile</p>
      </div>

      <ErrorBoundary><TasteProfileSummary /></ErrorBoundary>

      <Section title="Discover" description="New tracks from artists near your listening habits.">
        <ErrorBoundary><DiscoverSection /></ErrorBoundary>
      </Section>

      <Section title="Recommended" description="Songs from your library ranked by your current taste.">
        <ErrorBoundary><DiscoveryFeed /></ErrorBoundary>
      </Section>

      <Section title="Listening Goals" description="Set weekly targets and track your progress.">
        <ErrorBoundary><GoalsSection /></ErrorBoundary>
      </Section>
    </div>
  )
}
