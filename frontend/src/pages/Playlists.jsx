import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Ban, CalendarClock, ChevronDown, ChevronUp, Clock, ExternalLink, Info, Music, Pause, Pin, Play, Plus, RefreshCw, RotateCcw, Shuffle, SkipForward, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth, useCapability } from '../contexts/AuthContext'
import { usePlayer } from '../contexts/PlayerContext'
import Spinner from '../components/ui/Spinner'
import ErrorBoundary from '../components/ui/ErrorBoundary'
import CapabilityNotice from '../components/ui/CapabilityNotice'

const CONTEXTS = [
  { value: '', label: 'No context' },
  { value: 'focus', label: 'Focus' },
  { value: 'workout', label: 'Workout' },
  { value: 'chill', label: 'Chill' },
  { value: 'late-night', label: 'Late Night' },
]

const QUICK_FEEDBACK = [
  { action: 'like', icon: ThumbsUp, tip: 'Like' },
  { action: 'dislike', icon: ThumbsDown, tip: 'Dislike' },
  { action: 'skip', icon: SkipForward, tip: 'Skip' },
  { action: 'never_show', icon: Ban, tip: 'Never show' },
]

export function isSpotifyTokenExpired(error) {
  return error?.data?.detail === 'spotify_token_expired'
}

export function isLoggedOutError(error) {
  if (isSpotifyTokenExpired(error)) return false
  const text = `${error?.message || ''} ${error?.data?.detail || ''} ${error?.data?.message || ''}`.toLowerCase()
  return error?.status === 401 || text.includes('user not logged in')
}

// Turn the per-track score_breakdown the backend already computes into a few
// human-readable chips. Exported for unit testing.
export function explanationChips(breakdown) {
  if (!breakdown) return []
  const pct = (v) => `${Math.round((v || 0) * 100)}%`
  const chips = []
  if (breakdown.tfidf_similarity != null) chips.push(`Tag match ${pct(breakdown.tfidf_similarity)}`)
  if (breakdown.familiarity_score != null) chips.push(`Familiarity ${pct(breakdown.familiarity_score)}`)
  if ((breakdown.co_occurrence_boost || 0) > 0) chips.push('Often heard together')
  if ((breakdown.feedback_events || 0) > 0) {
    const n = breakdown.feedback_events
    chips.push(`${n} feedback signal${n === 1 ? '' : 's'}`)
  }
  return chips
}

function WhyDetails({ reasons, breakdown }) {
  const [open, setOpen] = useState(false)
  const list = (reasons || []).filter(Boolean)
  const chips = explanationChips(breakdown)
  if (!list.length && !chips.length) return null

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <Info className="w-3 h-3" /> {open ? 'Hide reasons' : 'Why this pick?'}
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 border-l border-zinc-800 pl-2">
          {list.length > 0 && (
            <ul className="space-y-0.5">
              {list.map(r => (
                <li key={r} className="text-[11px] text-zinc-400 first-letter:capitalize">• {r}</li>
              ))}
            </ul>
          )}
          {chips.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {chips.map(c => (
                <span key={c} className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px]">{c}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PlaylistRationale({ summary }) {
  if (!summary) return null
  const tags = (summary.dominant_tags || []).filter(Boolean).slice(0, 5)
  const genres = (summary.dominant_genres || []).filter(Boolean).slice(0, 3)
  const familiarPct = summary.familiar_ratio != null ? Math.round(summary.familiar_ratio * 100) : null
  if (!tags.length && !genres.length && familiarPct == null) return null

  return (
    <div className="px-5 py-3 border-b border-zinc-800 bg-zinc-950/40 space-y-2">
      <p className="text-xs font-medium text-zinc-300">Why this playlist</p>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map(t => (
            <span key={t} className="px-2 py-0.5 rounded-full bg-brand/10 text-brand text-xs">{t}</span>
          ))}
        </div>
      )}
      <p className="text-xs text-zinc-500">
        {genres.length > 0 && <>Built around {genres.join(', ')}. </>}
        {familiarPct != null && <>{familiarPct}% familiar / {100 - familiarPct}% discovery. </>}
        {summary.diversity_summary}
      </p>
    </div>
  )
}

function QualityNotes({ preview }) {
  const controls = preview?.quality_controls
  const notes = controls?.notes || []
  const warnings = preview?.warnings || []
  const summary = preview?.preview_summary
  if (!summary && !notes.length && !warnings.length) return null

  return (
    <div className="px-5 py-3 border-b border-zinc-800 bg-zinc-950/40 space-y-2">
      {summary && (
        <p className="text-sm text-zinc-300">{summary}</p>
      )}
      {notes.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {notes.map(note => (
            <span key={note} className="px-2.5 py-1 rounded-md bg-zinc-800 text-zinc-300 text-xs">
              {note}
            </span>
          ))}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map(warning => (
            <p key={warning} className="text-xs text-yellow-300">{warning}</p>
          ))}
        </div>
      )}
    </div>
  )
}

function TrackRow({ track, index, editable, onMove, onRemove, onReplace, onPin }) {
  const { play, isPlaying } = usePlayer()
  const song = track.song
  const active = isPlaying(song)
  const [feedback, setFeedback] = useState(null)
  const canGiveFeedback = useCapability('submit_feedback')

  async function sendFeedback(action) {
    if (!song?.id) return
    try {
      await api.post('/insights/feedback', { song_id: song.id, action })
      setFeedback(action)
    } catch (e) { console.error(e) }
  }

  return (
    <div className={`flex items-center gap-3 p-2 rounded-lg group transition-colors ${active ? 'bg-brand/10' : 'hover:bg-zinc-800'}`}>
      <span className="w-6 text-center text-xs text-zinc-600 group-hover:hidden">{index + 1}</span>
      <button onClick={() => song?.preview_url && play(song)} className="w-6 hidden group-hover:flex items-center justify-center">
        {active ? <Pause className="w-3.5 h-3.5 text-brand" /> : <Play className="w-3.5 h-3.5 text-zinc-400" />}
      </button>

      {song?.image_url ? (
        <img src={song.image_url} alt="" className="w-10 h-10 rounded object-cover shrink-0" />
      ) : (
        <div className="w-10 h-10 rounded bg-zinc-800 flex items-center justify-center shrink-0">
          <Music className="w-4 h-4 text-zinc-600" />
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium truncate ${active ? 'text-brand' : 'text-white'}`}>{song?.title}</p>
        <p className="text-xs text-zinc-400 truncate">{song?.artist}</p>
        <WhyDetails reasons={track.explanation?.reasons} breakdown={track.score_breakdown} />
      </div>

      {canGiveFeedback && <div className="hidden group-hover:flex items-center gap-1 shrink-0 self-start mt-1">
        {QUICK_FEEDBACK.map(({ action, icon: Icon, tip }) => (
          <button
            key={action}
            title={tip}
            aria-label={tip}
            onClick={() => sendFeedback(action)}
            className={`w-6 h-6 rounded flex items-center justify-center transition-colors ${feedback === action ? 'text-brand' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <Icon className="w-3 h-3" />
          </button>
        ))}
      </div>}

      <span className="text-xs text-zinc-600 shrink-0 group-hover:hidden">{track.final_score?.toFixed(2)}</span>
      {editable && <div className="hidden group-hover:flex items-center gap-0.5">
        <button type="button" title="Move up" onClick={() => onMove(index, -1)} className="p-1 text-zinc-500 hover:text-white"><ArrowUp className="h-3 w-3" /></button>
        <button type="button" title="Move down" onClick={() => onMove(index, 1)} className="p-1 text-zinc-500 hover:text-white"><ArrowDown className="h-3 w-3" /></button>
        <button type="button" title={track.is_pinned ? 'Unpin' : 'Pin'} onClick={() => onPin(track)} className={`p-1 ${track.is_pinned ? 'text-brand' : 'text-zinc-500 hover:text-white'}`}><Pin className="h-3 w-3" /></button>
        <button type="button" title="Replace" disabled={track.is_pinned} onClick={() => onReplace(track)} className="p-1 text-zinc-500 hover:text-white disabled:opacity-30"><RefreshCw className="h-3 w-3" /></button>
        <button type="button" title="Remove" onClick={() => onRemove(track)} className="p-1 text-zinc-500 hover:text-red-400"><Trash2 className="h-3 w-3" /></button>
      </div>}
    </div>
  )
}

function HistoryTab() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [detail, setDetail] = useState({})

  useEffect(() => {
    api.get('/playlists/generated')
      .then(d => setItems(d.items || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  async function toggleExpand(id) {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    if (!detail[id]) {
      try {
        const d = await api.get(`/playlists/generated/${id}`)
        setDetail(prev => ({ ...prev, [id]: d }))
      } catch (e) { console.error(e) }
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner /></div>
  if (!items.length) return <div className="text-center py-20 text-zinc-500">No playlists generated yet.</div>

  return (
    <div className="space-y-2">
      {items.map(pl => (
        <div key={pl.id} className="bg-zinc-900 rounded-xl border border-zinc-800 overflow-hidden">
          <button onClick={() => toggleExpand(pl.id)} className="w-full flex items-center gap-4 px-5 py-4 hover:bg-zinc-800 transition-colors text-left">
            <div className="flex-1 min-w-0">
              <p className="text-white font-medium truncate">{pl.name}</p>
              <p className="text-zinc-500 text-xs mt-0.5">
                {new Date(pl.created_at).toLocaleDateString()} - {pl.context_type || 'no context'}{pl.spotify_playlist_id && ' - saved to Spotify'}
              </p>
            </div>
            {expanded === pl.id ? <ChevronUp className="w-4 h-4 text-zinc-500 shrink-0" /> : <ChevronDown className="w-4 h-4 text-zinc-500 shrink-0" />}
          </button>

          {expanded === pl.id && detail[pl.id] && (
            <div className="border-t border-zinc-800">
              {detail[pl.id].summary && <PlaylistRationale summary={detail[pl.id].summary} />}
              <div className="p-2 space-y-0.5">
                {(detail[pl.id].tracks || []).map((track, i) => {
                  const song = track.song
                  return (
                    <div key={track.id ?? i} className="flex items-start gap-3 px-2 py-1.5 rounded-lg hover:bg-zinc-800">
                      <span className="w-5 text-xs text-zinc-600 text-center mt-0.5">{i + 1}</span>
                      {song?.image_url
                        ? <img src={song.image_url} alt="" className="w-8 h-8 rounded object-cover shrink-0" />
                        : <div className="w-8 h-8 rounded bg-zinc-800 flex items-center justify-center shrink-0"><Music className="w-3 h-3 text-zinc-600" /></div>}
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm truncate">{song?.title}</p>
                        <p className="text-zinc-500 text-xs truncate">{song?.artist}</p>
                        <WhyDetails reasons={track.explanation?.reasons} breakdown={track.score_breakdown} />
                      </div>
                      {song?.spotify_id && (
                        <a href={`https://open.spotify.com/track/${song.spotify_id}`} target="_blank" rel="noopener noreferrer" className="text-zinc-600 hover:text-brand shrink-0 mt-0.5">
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const SCHEDULE_CADENCES = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'daily', label: 'Daily' },
]

function formatScheduleDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function SchedulesTab() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [form, setForm] = useState({ cadence: 'weekly', context_type: '', max_tracks: 25 })
  const canManageSchedules = useCapability('manage_schedules')

  function load() {
    setLoading(true)
    api.get('/playlists/schedules')
      .then(d => setItems(d.items || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function createSchedule() {
    setCreating(true)
    try {
      await api.post('/playlists/schedules', {
        cadence: form.cadence,
        context_type: form.context_type || null,
        max_tracks: Number(form.max_tracks),
      })
      load()
    } catch (e) { console.error(e) }
    finally { setCreating(false) }
  }

  async function runNow(id) {
    setBusyId(id)
    try {
      await api.post(`/playlists/schedules/${id}/run`)
      load()
    } catch (e) { console.error(e) }
    finally { setBusyId(null) }
  }

  async function remove(id) {
    try {
      await api.delete(`/playlists/schedules/${id}`)
      setItems(prev => prev.filter(s => s.id !== id))
    } catch (e) { console.error(e) }
  }

  return (
    <div className="space-y-4">
      <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800 space-y-4">
        <div>
          <h2 className="text-white font-semibold">Auto-refresh a playlist</h2>
          <p className="text-zinc-400 text-sm mt-1">
            We regenerate a fresh playlist from your latest taste on this cadence. Open this page to pick up due refreshes; the newest one waits in History.
          </p>
        </div>
        {!canManageSchedules && <CapabilityNotice>Schedules are read-only in the shared demo. Connect Spotify to create automatic playlists.</CapabilityNotice>}
        {canManageSchedules && <div className="flex flex-wrap gap-3 items-end">
          <div className="space-y-1">
            <label className="text-xs text-zinc-400">Cadence</label>
            <select
              value={form.cadence}
              onChange={e => setForm(f => ({ ...f, cadence: e.target.value }))}
              className="bg-zinc-800 border border-zinc-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-brand"
            >
              {SCHEDULE_CADENCES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-400">Context</label>
            <select
              value={form.context_type}
              onChange={e => setForm(f => ({ ...f, context_type: e.target.value }))}
              className="bg-zinc-800 border border-zinc-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-brand"
            >
              {CONTEXTS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-400">Tracks: {form.max_tracks}</label>
            <input
              type="range" min={5} max={50} step={5}
              value={form.max_tracks}
              onChange={e => setForm(f => ({ ...f, max_tracks: e.target.value }))}
              className="w-32 accent-brand"
            />
          </div>
          <button
            onClick={createSchedule}
            disabled={creating}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-brand text-black hover:bg-green-400 disabled:opacity-60"
          >
            {creating ? <Spinner size="sm" /> : <Plus className="w-4 h-4" />}
            Add schedule
          </button>
        </div>}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-zinc-500">No schedules yet.</div>
      ) : (
        <div className="space-y-2">
          {items.map(s => (
            <div key={s.id} className="bg-zinc-900 rounded-xl border border-zinc-800 px-5 py-4 flex items-center gap-4">
              <div className="w-9 h-9 rounded-lg bg-brand/10 flex items-center justify-center shrink-0">
                <CalendarClock className="w-4 h-4 text-brand" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-medium capitalize">
                  {s.cadence}{s.context_type ? ` · ${s.context_type}` : ''} · {s.max_tracks} tracks
                </p>
                <p className="text-zinc-500 text-xs mt-0.5">
                  Next {formatScheduleDate(s.next_run_at)} · Last run {formatScheduleDate(s.last_run_at)}
                </p>
                {s.last_error && <p className="mt-1 text-xs text-red-400">Last run failed: {s.last_error}</p>}
              </div>
              {canManageSchedules && <button
                onClick={() => runNow(s.id)}
                disabled={busyId === s.id}
                title="Run now"
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-800 text-zinc-300 rounded-lg hover:bg-zinc-700 disabled:opacity-60"
              >
                {busyId === s.id ? <Spinner size="sm" /> : <RefreshCw className="w-3 h-3" />}
                Run now
              </button>}
              {canManageSchedules && <button
                onClick={() => remove(s.id)}
                title="Delete schedule"
                aria-label="Delete schedule"
                className="w-7 h-7 rounded flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-zinc-800 shrink-0"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Playlists() {
  const navigate = useNavigate()
  const { login, can } = useAuth()
  const [tab, setTab] = useState('generate')
  const [config, setConfig] = useState({ context_type: '', max_tracks: 20, diversity: 0.5, familiarity: 0.5 })
  const [preview, setPreview] = useState(null)
  const [generating, setGen] = useState(false)
  const [pushing, setPush] = useState(false)
  const [pushed, setPushed] = useState(null)
  const [error, setError] = useState(null)
  const [spotifyExpired, setSpotifyExpired] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [draftName, setDraftName] = useState('')

  async function generate() {
    setGen(true)
    setError(null)
    setPushed(null)
    setSpotifyExpired(false)
    try {
      const res = await api.post('/playlists/preview', {
        ...config,
        context_type: config.context_type || null,
        max_tracks: Number(config.max_tracks),
        diversity: Number(config.diversity),
        familiarity: Number(config.familiarity),
      })
      setPreview(res)
      setDraftName(res.generated_playlist?.name || '')
    } catch (e) {
      setError(e.message)
    } finally {
      setGen(false)
    }
  }

  async function handleReconnectSpotify() {
    setReconnecting(true)
    try {
      await login({ skipLogout: true })
      setSpotifyExpired(false)
      // Retry the push automatically after reconnect
      await pushToSpotify()
    } catch (e) {
      setError(e.message || 'Reconnect failed. Please try again.')
    } finally {
      setReconnecting(false)
    }
  }

  async function pushToSpotify() {
    if (!preview?.generated_playlist?.id) return
    setPush(true)
    setError(null)
    setSpotifyExpired(false)
    try {
      const res = await api.post(`/playlists/generated/${preview.generated_playlist.id}/create`)
      setPushed(res.playlist)
      setPreview(prev => prev ? { ...prev, generated_playlist: res.generated_playlist } : prev)
    } catch (e) {
      if (isSpotifyTokenExpired(e)) {
        setSpotifyExpired(true)
        return
      }
      if (isLoggedOutError(e)) {
        navigate('/login', { replace: true })
        return
      }
      setError(e.message)
    } finally {
      setPush(false)
    }
  }

  async function saveName() {
    const id = preview?.generated_playlist?.id
    const name = draftName.trim()
    if (!id || !name) { setEditingName(false); return }
    try {
      const updated = await api.patch(`/playlists/generated/${id}/name`, { name })
      setPreview(prev => prev ? { ...prev, generated_playlist: updated } : prev)
      setDraftName(updated.name)
    } catch (e) {
      setError(e.message)
    } finally {
      setEditingName(false)
    }
  }

  function applyEditedPlaylist(generatedPlaylist) {
    setPreview(prev => prev ? { ...prev, generated_playlist: generatedPlaylist } : prev)
  }

  async function moveTrack(index, direction) {
    const next = [...tracks]
    const target = index + direction
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    try {
      applyEditedPlaylist(await api.patch(`/playlists/generated/${preview.generated_playlist.id}/tracks/reorder`, { track_ids: next.map(t => t.id) }))
    } catch (e) { setError(e.message) }
  }

  async function removeTrack(track) {
    try { applyEditedPlaylist(await api.delete(`/playlists/generated/${preview.generated_playlist.id}/tracks/${track.id}`)) }
    catch (e) { setError(e.message) }
  }

  async function replaceTrack(track) {
    try { applyEditedPlaylist(await api.post(`/playlists/generated/${preview.generated_playlist.id}/tracks/${track.id}/replace`)) }
    catch (e) { setError(e.message) }
  }

  async function pinTrack(track) {
    try {
      await api.patch(`/playlists/generated/${preview.generated_playlist.id}/tracks/${track.id}`, { is_pinned: !track.is_pinned })
      applyEditedPlaylist({ ...preview.generated_playlist, tracks: tracks.map(item => item.id === track.id ? { ...item, is_pinned: !item.is_pinned } : item) })
    } catch (e) { setError(e.message) }
  }

  const tracks = preview?.generated_playlist?.tracks || []
  const spotifyPlaylistId = pushed?.id || preview?.generated_playlist?.spotify_playlist_id

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-3xl">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Playlists</h1>
          <p className="text-zinc-400 text-sm mt-1">Generate playlists using your taste profile</p>
        </div>
        <div className="flex gap-1 bg-zinc-800 rounded-lg p-1">
          {['generate', 'schedules', 'history'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${tab === t ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:text-white'}`}
            >
              {t === 'history'
                ? <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" />History</span>
                : t === 'schedules'
                ? <span className="flex items-center gap-1.5"><CalendarClock className="w-3.5 h-3.5" />Schedules</span>
                : 'Generate'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'history' && <ErrorBoundary><HistoryTab /></ErrorBoundary>}
      {tab === 'schedules' && <ErrorBoundary><SchedulesTab /></ErrorBoundary>}
      {tab === 'generate' && (
        <>
          <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800 space-y-4">
            <h2 className="text-white font-semibold">Settings</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Context</label>
                <select value={config.context_type} onChange={e => setConfig(c => ({ ...c, context_type: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-brand">
                  {CONTEXTS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Tracks: {config.max_tracks}</label>
                <input type="range" min={5} max={50} step={5} value={config.max_tracks} onChange={e => setConfig(c => ({ ...c, max_tracks: e.target.value }))} className="w-full accent-brand" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Diversity: {config.diversity}</label>
                <input type="range" min={0} max={1} step={0.1} value={config.diversity} onChange={e => setConfig(c => ({ ...c, diversity: e.target.value }))} className="w-full accent-brand" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Familiarity: {config.familiarity}</label>
                <input type="range" min={0} max={1} step={0.1} value={config.familiarity} onChange={e => setConfig(c => ({ ...c, familiarity: e.target.value }))} className="w-full accent-brand" />
              </div>
            </div>
            <button onClick={generate} disabled={generating} className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand text-black font-semibold text-sm rounded-lg hover:bg-green-400 transition-colors disabled:opacity-60">
              {generating ? <Spinner size="sm" /> : <Shuffle className="w-4 h-4" />}
              {generating ? 'Generating...' : 'Generate Playlist'}
            </button>
          </div>

          {error && <p className="text-red-400 text-sm bg-red-400/10 rounded-lg px-4 py-2.5">{error}</p>}

          {spotifyExpired && (
            <div className="flex items-center justify-between gap-4 bg-yellow-900/20 border border-yellow-700/40 rounded-xl px-4 py-3">
              <div className="min-w-0">
                <p className="text-yellow-300 text-sm font-medium">Your Spotify session expired</p>
                <p className="text-zinc-400 text-xs mt-0.5">Reconnect Spotify to save this playlist — your preview is still here.</p>
              </div>
              <button
                onClick={handleReconnectSpotify}
                disabled={reconnecting}
                className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-black font-semibold rounded-lg hover:bg-green-400 transition-colors disabled:opacity-60"
              >
                {reconnecting ? <Spinner size="sm" /> : <RefreshCw className="w-3 h-3" />}
                {reconnecting ? 'Connecting…' : 'Reconnect'}
              </button>
            </div>
          )}

          {pushed && (
            <div className="flex items-center justify-between gap-4 bg-brand/10 border border-brand/20 rounded-xl px-4 py-3">
              <div className="min-w-0">
                <p className="text-brand text-sm font-medium">Playlist saved to Spotify!</p>
                <p className="text-zinc-400 text-xs mt-0.5 truncate">{pushed.name}</p>
              </div>
              <a
                href={`https://open.spotify.com/playlist/${pushed.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-black font-semibold rounded-lg hover:bg-green-400 transition-colors shrink-0"
              >
                <ExternalLink className="w-3 h-3" /> Open
              </a>
            </div>
          )}

          {preview && (
            <div className="bg-zinc-900 rounded-xl border border-zinc-800 overflow-hidden">
              <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-zinc-800">
                <div className="min-w-0 flex-1">
                  {editingName ? (
                    <input
                      value={draftName}
                      onChange={e => setDraftName(e.target.value)}
                      onBlur={saveName}
                      onKeyDown={e => {
                        if (e.key === 'Enter') saveName()
                        if (e.key === 'Escape') {
                          setDraftName(preview.generated_playlist?.name || '')
                          setEditingName(false)
                        }
                      }}
                      autoFocus
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-sm font-semibold text-white focus:outline-none focus:border-brand"
                    />
                  ) : (
                    <button type="button" disabled={!can('mutate_library')} onClick={() => { setDraftName(preview.generated_playlist?.name || ''); setEditingName(true) }} className="text-left max-w-full disabled:cursor-default">
                      <h2 className="text-white font-semibold truncate">{preview.generated_playlist?.name}</h2>
                    </button>
                  )}
                  <p className="text-zinc-400 text-xs mt-0.5">{tracks.length} tracks - {preview.recommendation_candidates} candidates</p>
                  <p className="text-zinc-500 text-xs mt-1">This playlist exists locally - click to push it to your Spotify account.</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button onClick={generate} disabled={generating} title="Regenerate" className="w-8 h-8 text-zinc-400 border border-zinc-700 rounded-lg hover:bg-zinc-800 transition-colors flex items-center justify-center disabled:opacity-60">
                    {generating ? <Spinner size="sm" /> : <RotateCcw className="w-3.5 h-3.5" />}
                  </button>
                  {spotifyPlaylistId ? (
                    <a
                      href={`https://open.spotify.com/playlist/${spotifyPlaylistId}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-black font-semibold rounded-lg hover:bg-green-400 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" /> Open in Spotify ↗
                    </a>
                  ) : can('create_spotify_playlists') ? (
                    <button onClick={pushToSpotify} disabled={pushing} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-black font-medium rounded-lg hover:bg-green-400 transition-colors disabled:opacity-60">
                      {pushing ? <Spinner size="sm" /> : <ExternalLink className="w-3 h-3" />}
                      {pushing ? 'Creating...' : 'Save to Spotify'}
                    </button>
                  ) : (
                    <span className="text-xs text-zinc-400">Preview only in demo</span>
                  )}
                </div>
              </div>

              <PlaylistRationale summary={preview.generated_playlist?.summary} />
              <QualityNotes preview={preview} />

              <div className="p-2 space-y-0.5">
                {tracks.map((track, i) => (
                  <TrackRow
                    key={track.id ?? i}
                    track={track}
                    index={i}
                    editable={can('mutate_library') && !spotifyPlaylistId}
                    onMove={moveTrack}
                    onRemove={removeTrack}
                    onReplace={replaceTrack}
                    onPin={pinTrack}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
