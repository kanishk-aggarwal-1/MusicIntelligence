import { useEffect, useId, useRef, useState } from 'react'
import { X, EyeOff, Eye, RefreshCw, ThumbsUp, ThumbsDown, SkipForward, Ban, Heart, Calendar, Headphones, ListMusic } from 'lucide-react'
import { api } from '../../lib/api'
import { usePlayer } from '../../contexts/PlayerContext'
import Spinner from './Spinner'
import CapabilityNotice from './CapabilityNotice'
import { useCapability } from '../../contexts/AuthContext'

function formatDate(value) {
  if (!value) return null
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const FEEDBACK = [
  { action: 'like',          label: 'Like',           icon: ThumbsUp,    color: 'text-green-400'  },
  { action: 'more_like_this',label: 'More like this',  icon: Heart,       color: 'text-pink-400'   },
  { action: 'dislike',       label: 'Dislike',         icon: ThumbsDown,  color: 'text-red-400'    },
  { action: 'skip',          label: 'Skip',            icon: SkipForward, color: 'text-yellow-400' },
  { action: 'never_show',    label: 'Never show',      icon: Ban,         color: 'text-red-600'    },
]

const STATUS_STYLE = {
  complete: 'text-green-400 bg-green-400/10',
  partial:  'text-yellow-400 bg-yellow-400/10',
  pending:  'text-blue-400 bg-blue-400/10',
  failed:   'text-red-400 bg-red-400/10',
}

export default function SongModal({ song: initial, onClose, onUpdate }) {
  const dialogRef = useRef(null)
  const titleId = useId()
  const { play, isPlaying } = usePlayer()
  const [song, setSong]             = useState(initial)
  const [submittedFeedback, setFb]  = useState(null)
  const [actionLoading, setAL]      = useState(false)
  const [enriching, setEnriching]   = useState(false)
  const [enrichMsg, setEnrichMsg]   = useState(null)
  const canMutateLibrary = useCapability('mutate_library')
  const canGiveFeedback = useCapability('submit_feedback')
  const canEnrich = useCapability('enrich_metadata')

  useEffect(() => {
    const previousFocus = document.activeElement
    dialogRef.current?.focus()
    function onKeyDown(event) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previousFocus?.focus?.()
    }
  }, [onClose])

  async function hide() {
    setAL(true)
    try {
      await api.post(`/songs/${song.id}/hide`)
      const updated = { ...song, is_deleted: true }
      setSong(updated); onUpdate?.(updated)
    } finally { setAL(false) }
  }

  async function restore() {
    setAL(true)
    try {
      await api.post(`/songs/${song.id}/restore`)
      const updated = { ...song, is_deleted: false }
      setSong(updated); onUpdate?.(updated)
    } finally { setAL(false) }
  }

  async function retryEnrichment() {
    setEnriching(true); setEnrichMsg(null)
    try {
      const res = await api.post(`/songs/${song.id}/retry-enrichment`)
      const updated = { ...song, enrichment_status: res.enrichment_status, genre: res.genre }
      setSong(updated); onUpdate?.(updated)
      setEnrichMsg(`Done — status: ${res.enrichment_status}`)
    } catch (e) {
      setEnrichMsg(`Error: ${e.message}`)
    } finally { setEnriching(false) }
  }

  async function sendFeedback(action) {
    try {
      await api.post('/insights/feedback', { song_id: song.id, action })
      setFb(action)
    } catch (e) { console.error(e) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="bg-zinc-900 rounded-2xl w-full max-w-sm border border-zinc-800 overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Art */}
        <div className="relative">
          {song.image_url
            ? <img src={song.image_url} alt="" className="w-full aspect-square object-cover" />
            : <div className="w-full aspect-square bg-zinc-800 flex items-center justify-center text-5xl">♪</div>}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close song details"
            className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80"
          ><X className="w-4 h-4" /></button>
          {song.preview_url && (
            <button
              type="button"
              onClick={() => play(song)}
              aria-label={isPlaying(song) ? `Pause ${song.title}` : `Play ${song.title}`}
              className="absolute bottom-3 right-3 w-10 h-10 rounded-full bg-brand flex items-center justify-center text-black font-bold text-lg hover:bg-green-400"
            >{isPlaying(song) ? '⏸' : '▶'}</button>
          )}
        </div>

        <div className="p-4 space-y-4">
          {/* Info */}
          <div>
            <h2 id={titleId} className="text-white font-bold truncate">{song.title}</h2>
            <p className="text-zinc-400 text-sm truncate">{song.artist}</p>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {song.genre && <span className="text-xs px-2 py-0.5 bg-zinc-800 text-brand rounded-full">{song.genre}</span>}
              <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[song.enrichment_status] || 'text-zinc-500 bg-zinc-800'}`}>
                {song.enrichment_status}
              </span>
              {song.is_deleted && <span className="text-xs px-2 py-0.5 bg-red-500/10 text-red-400 rounded-full">hidden</span>}
            </div>
            {/* Listening stats */}
            <div className="flex gap-3 mt-3 flex-wrap">
              {song.listening_count > 0 && (
                <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <Headphones className="w-3.5 h-3.5 text-zinc-600" />
                  <span>{song.listening_count} play{song.listening_count !== 1 ? 's' : ''}</span>
                </div>
              )}
              {song.last_listened_at && (
                <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <Calendar className="w-3.5 h-3.5 text-zinc-600" />
                  <span>Last: {formatDate(song.last_listened_at)}</span>
                </div>
              )}
              {song.playlist_inclusion_count > 0 && (
                <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <ListMusic className="w-3.5 h-3.5 text-zinc-600" />
                  <span>In {song.playlist_inclusion_count} playlist{song.playlist_inclusion_count !== 1 ? 's' : ''}</span>
                </div>
              )}
            </div>
          </div>

          {/* Feedback */}
          {canGiveFeedback && <div>
            <p className="text-zinc-500 text-xs mb-2 uppercase tracking-wide">Feedback</p>
            <div className="flex flex-wrap gap-1.5">
              {FEEDBACK.map(({ action, label, icon: Icon, color }) => (
                <button
                  key={action}
                  type="button"
                  onClick={() => sendFeedback(action)}
                  aria-pressed={submittedFeedback === action}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs border transition-all ${
                    submittedFeedback === action
                      ? `${color} border-current bg-current/10 font-medium`
                      : 'text-zinc-400 border-zinc-700 hover:border-zinc-500 hover:text-zinc-200'
                  }`}
                >
                  <Icon className="w-3 h-3" />{label}
                </button>
              ))}
            </div>
          </div>}

          {/* Actions */}
          {(canMutateLibrary || canEnrich) ? <div className="flex gap-2 flex-wrap pt-3 border-t border-zinc-800">
            {canEnrich &&
            <button
              onClick={retryEnrichment}
              disabled={enriching}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              {enriching ? <Spinner size="sm" /> : <RefreshCw className="w-3 h-3" />}
              Retry enrichment
            </button>}
            {canMutateLibrary && (song.is_deleted
              ? <button onClick={restore} disabled={actionLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-zinc-800 text-green-400 hover:bg-zinc-700 disabled:opacity-50">
                  <Eye className="w-3 h-3" />Restore
                </button>
              : <button onClick={hide} disabled={actionLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-zinc-800 text-red-400 hover:bg-zinc-700 disabled:opacity-50">
                  <EyeOff className="w-3 h-3" />Hide
                </button>
            )}
          </div> : <CapabilityNotice>Guest mode keeps the showcased library read-only.</CapabilityNotice>}
          {enrichMsg && <p role="status" aria-live="polite" className={`text-xs ${enrichMsg.startsWith('Error') ? 'text-red-400' : 'text-green-400'}`}>{enrichMsg}</p>}
        </div>
      </div>
    </div>
  )
}
