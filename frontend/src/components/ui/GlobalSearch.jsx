import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard, ListMusic, Music, Music2, Search, Tag, Heart, Wrench, X } from 'lucide-react'
import { api } from '../../lib/api'
import SongModal from './SongModal'
import Spinner from './Spinner'

const PAGES = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, keywords: ['home', 'stats', 'overview', 'charts'] },
  { path: '/songs',     label: 'Songs',     icon: Music2,          keywords: ['library', 'tracks', 'all songs'] },
  { path: '/browse',    label: 'Browse',    icon: Tag,             keywords: ['tags', 'genres', 'explore'] },
  { path: '/for-you',   label: 'For You',   icon: Heart,           keywords: ['recommendations', 'discover', 'goals'] },
  { path: '/playlists', label: 'Playlists', icon: ListMusic,        keywords: ['generate', 'create', 'spotify'] },
  { path: '/features',  label: 'Tools',     icon: Wrench,           keywords: ['enrichment', 'dedup', 'maintenance'] },
]

export default function GlobalSearch() {
  const [open, setOpen]               = useState(false)
  const [query, setQuery]             = useState('')
  const [songs, setSongs]             = useState([])
  const [loading, setLoading]         = useState(false)
  const [activeIdx, setActiveIdx]     = useState(0)
  const [selectedSong, setSelectedSong] = useState(null)
  const inputRef  = useRef(null)
  const navigate  = useNavigate()

  // ── Open / close ──────────────────────────────────────────────────────────
  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setSongs([])
    setActiveIdx(0)
  }, [])

  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Focus on open
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30)
  }, [open])

  // ── Debounced song search ─────────────────────────────────────────────────
  useEffect(() => {
    if (!open || !query.trim()) { setSongs([]); return }
    const t = setTimeout(() => {
      setLoading(true)
      api.get('/songs', { q: query.trim(), limit: 8, offset: 0 })
        .then(data => setSongs(data || []))
        .catch(() => setSongs([]))
        .finally(() => setLoading(false))
    }, 200)
    return () => clearTimeout(t)
  }, [query, open])

  // ── Results ───────────────────────────────────────────────────────────────
  const pageResults = query.trim()
    ? PAGES.filter(p =>
        p.label.toLowerCase().includes(query.toLowerCase()) ||
        p.keywords.some(k => k.includes(query.toLowerCase()))
      )
    : PAGES

  const allResults = [
    ...pageResults.map(p => ({ _type: 'page', ...p })),
    ...songs.map(s =>       ({ _type: 'song', ...s })),
  ]

  // ── Selection ─────────────────────────────────────────────────────────────
  function select(item) {
    if (item._type === 'page') {
      navigate(item.path)
      close()
    } else {
      close()
      setSelectedSong(item)
    }
  }

  // ── Keyboard nav inside dialog ────────────────────────────────────────────
  function onDialogKey(e) {
    if (e.key === 'Escape') { close(); return }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, allResults.length - 1))
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    }
    if (e.key === 'Enter' && allResults[activeIdx]) {
      select(allResults[activeIdx])
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Trigger hint — visible in Sidebar via a separate button, or keyboard only */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[18vh] px-4 bg-black/50 backdrop-blur-sm"
          onClick={close}
        >
          <div
            className="bg-zinc-900 rounded-2xl border border-zinc-700 w-full max-w-lg shadow-2xl overflow-hidden"
            onClick={e => e.stopPropagation()}
            onKeyDown={onDialogKey}
          >
            {/* Search input */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800">
              <Search className="w-4 h-4 text-zinc-500 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={e => { setQuery(e.target.value); setActiveIdx(0) }}
                placeholder="Search songs or go to a page…"
                className="flex-1 bg-transparent text-white text-sm outline-none placeholder-zinc-500"
              />
              {loading && <Spinner size="sm" />}
              <button onClick={close} className="text-zinc-600 hover:text-zinc-400 shrink-0">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Result list */}
            <div className="max-h-80 overflow-y-auto py-1">
              {/* Pages */}
              {pageResults.length > 0 && (
                <div>
                  {!query.trim() && (
                    <p className="px-4 pt-2 pb-1 text-xs text-zinc-600 uppercase tracking-wide">Navigate</p>
                  )}
                  {pageResults.map((page, i) => {
                    const Icon = page.icon
                    const active = i === activeIdx
                    return (
                      <button
                        key={page.path}
                        onClick={() => select({ _type: 'page', ...page })}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors ${
                          active ? 'bg-zinc-800 text-white' : 'text-zinc-300 hover:bg-zinc-800/60'
                        }`}
                      >
                        <Icon className="w-4 h-4 text-zinc-500 shrink-0" />
                        {page.label}
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Songs */}
              {songs.length > 0 && (
                <div>
                  <p className="px-4 pt-3 pb-1 text-xs text-zinc-600 uppercase tracking-wide">Songs</p>
                  {songs.map((song, i) => {
                    const idx = pageResults.length + i
                    const active = idx === activeIdx
                    return (
                      <button
                        key={song.id}
                        onClick={() => select({ _type: 'song', ...song })}
                        className={`w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors ${
                          active ? 'bg-zinc-800 text-white' : 'text-zinc-300 hover:bg-zinc-800/60'
                        }`}
                      >
                        {song.image_url ? (
                          <img src={song.image_url} alt="" className="w-8 h-8 rounded object-cover shrink-0" />
                        ) : (
                          <div className="w-8 h-8 rounded bg-zinc-800 flex items-center justify-center shrink-0">
                            <Music className="w-3.5 h-3.5 text-zinc-600" />
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-white">{song.title}</p>
                          <p className="text-xs text-zinc-500 truncate">{song.artist}</p>
                        </div>
                        {song.listening_count > 0 && (
                          <span className="text-xs text-zinc-600 shrink-0">{song.listening_count} plays</span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Empty */}
              {query.trim() && !loading && songs.length === 0 && pageResults.length === 0 && (
                <p className="px-4 py-5 text-sm text-zinc-500 text-center">No results for &ldquo;{query}&rdquo;</p>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 border-t border-zinc-800 flex items-center gap-4 text-xs text-zinc-600">
              <span><kbd className="font-mono bg-zinc-800 px-1 rounded">↑↓</kbd> navigate</span>
              <span><kbd className="font-mono bg-zinc-800 px-1 rounded">↵</kbd> select</span>
              <span><kbd className="font-mono bg-zinc-800 px-1 rounded">esc</kbd> close</span>
              <span className="ml-auto"><kbd className="font-mono bg-zinc-800 px-1 rounded">⌘K</kbd> toggle</span>
            </div>
          </div>
        </div>
      )}

      {/* Song detail modal — survives after search closes */}
      {selectedSong && (
        <SongModal
          song={selectedSong}
          onClose={() => setSelectedSong(null)}
          onUpdate={updated => setSelectedSong(updated)}
        />
      )}
    </>
  )
}
