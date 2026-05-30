import { useEffect, useState } from 'react'
import { Ban, ChevronDown, ChevronUp, Clock, ExternalLink, Music, Pause, Play, RotateCcw, Shuffle, SkipForward, ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../lib/api'
import { usePlayer } from '../contexts/PlayerContext'
import Spinner from '../components/ui/Spinner'
import ErrorBoundary from '../components/ui/ErrorBoundary'

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

function TrackRow({ track, index }) {
  const { play, isPlaying } = usePlayer()
  const song = track.song
  const active = isPlaying(song)
  const [feedback, setFeedback] = useState(null)

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
      </div>

      <div className="hidden group-hover:flex items-center gap-1 shrink-0">
        {QUICK_FEEDBACK.map(({ action, icon: Icon, tip }) => (
          <button
            key={action}
            title={tip}
            onClick={() => sendFeedback(action)}
            className={`w-6 h-6 rounded flex items-center justify-center transition-colors ${feedback === action ? 'text-brand' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            <Icon className="w-3 h-3" />
          </button>
        ))}
      </div>

      <span className="text-xs text-zinc-600 shrink-0 group-hover:hidden">{track.final_score?.toFixed(2)}</span>
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
            <div className="border-t border-zinc-800 p-2 space-y-0.5">
              {(detail[pl.id].tracks || []).map((track, i) => {
                const song = track.song
                return (
                  <div key={track.id ?? i} className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-zinc-800">
                    <span className="w-5 text-xs text-zinc-600 text-center">{i + 1}</span>
                    {song?.image_url
                      ? <img src={song.image_url} alt="" className="w-8 h-8 rounded object-cover shrink-0" />
                      : <div className="w-8 h-8 rounded bg-zinc-800 flex items-center justify-center shrink-0"><Music className="w-3 h-3 text-zinc-600" /></div>}
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-sm truncate">{song?.title}</p>
                      <p className="text-zinc-500 text-xs truncate">{song?.artist}</p>
                    </div>
                    {song?.spotify_id && (
                      <a href={`https://open.spotify.com/track/${song.spotify_id}`} target="_blank" rel="noopener noreferrer" className="text-zinc-600 hover:text-brand shrink-0">
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Playlists() {
  const [tab, setTab] = useState('generate')
  const [config, setConfig] = useState({ context_type: '', max_tracks: 20, diversity: 0.5, familiarity: 0.5 })
  const [preview, setPreview] = useState(null)
  const [generating, setGen] = useState(false)
  const [pushing, setPush] = useState(false)
  const [pushed, setPushed] = useState(null)
  const [error, setError] = useState(null)
  const [editingName, setEditingName] = useState(false)
  const [draftName, setDraftName] = useState('')

  async function generate() {
    setGen(true)
    setError(null)
    setPushed(null)
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

  async function pushToSpotify() {
    if (!preview?.generated_playlist?.id) return
    setPush(true)
    setError(null)
    try {
      const res = await api.post(`/playlists/generated/${preview.generated_playlist.id}/create`)
      setPushed(res.playlist)
      setPreview(prev => prev ? { ...prev, generated_playlist: res.generated_playlist } : prev)
    } catch (e) {
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
          {['generate', 'history'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${tab === t ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:text-white'}`}
            >
              {t === 'history' ? <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" />History</span> : 'Generate'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'history' && <ErrorBoundary><HistoryTab /></ErrorBoundary>}
      {tab !== 'history' && (
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
                    <button type="button" onClick={() => { setDraftName(preview.generated_playlist?.name || ''); setEditingName(true) }} className="text-left max-w-full">
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
                  ) : (
                    <button onClick={pushToSpotify} disabled={pushing} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-black font-medium rounded-lg hover:bg-green-400 transition-colors disabled:opacity-60">
                      {pushing ? <Spinner size="sm" /> : <ExternalLink className="w-3 h-3" />}
                      {pushing ? 'Creating...' : 'Save to Spotify'}
                    </button>
                  )}
                </div>
              </div>

              <QualityNotes preview={preview} />

              <div className="p-2 space-y-0.5">
                {tracks.map((track, i) => (
                  <TrackRow key={track.id ?? i} track={track} index={i} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
