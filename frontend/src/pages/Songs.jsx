import { useEffect, useMemo, useRef, useState } from 'react'
import { FixedSizeGrid, FixedSizeList } from 'react-window'
import { Ban, ExternalLink, Filter, Grid3X3, List, Music, Pause, Play, Search, SkipForward, ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../lib/api'
import SongCard from '../components/ui/SongCard'
import SongModal from '../components/ui/SongModal'
import Spinner from '../components/ui/Spinner'
import { usePlayer } from '../contexts/PlayerContext'

const STATUS_OPTIONS = [
  { value: '', label: 'All songs' },
  { value: 'complete', label: 'Complete' },
  { value: 'partial', label: 'Partial' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
]

const SORT_OPTIONS = [
  { value: 'recent', label: 'Recently played' },
  { value: 'plays', label: 'Most played' },
  { value: 'popularity', label: 'Popularity' },
  { value: 'alpha', label: 'A to Z' },
]

const QUICK_FEEDBACK = [
  { action: 'like', icon: ThumbsUp, tip: 'Like' },
  { action: 'dislike', icon: ThumbsDown, tip: 'Dislike' },
  { action: 'skip', icon: SkipForward, tip: 'Skip' },
  { action: 'never_show', icon: Ban, tip: 'Never show' },
]

function useElementSize() {
  const ref = useRef(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(entries => {
      const rect = entries[0].contentRect
      setSize({ width: rect.width, height: rect.height })
    })
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  return [ref, size]
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function SongListRow({ song, index, style }) {
  const { play, isPlaying } = usePlayer()
  const active = isPlaying(song)
  const [feedback, setFeedback] = useState(null)

  async function sendFeedback(action) {
    try {
      await api.post('/insights/feedback', { song_id: song.id, action })
      setFeedback(action)
    } catch (e) { console.error(e) }
  }

  return (
    <div style={style} className="px-1">
      <div className={`h-[68px] flex items-center gap-3 px-3 rounded-lg group transition-colors ${active ? 'bg-brand/10' : 'hover:bg-zinc-900'}`}>
        <span className="w-7 text-xs text-zinc-600 text-center group-hover:hidden">{index + 1}</span>
        <button
          type="button"
          onClick={() => song.preview_url && play(song)}
          className="w-7 hidden group-hover:flex items-center justify-center"
          disabled={!song.preview_url}
        >
          {active ? <Pause className="w-3.5 h-3.5 text-brand" /> : <Play className="w-3.5 h-3.5 text-zinc-400" />}
        </button>

        {song.image_url ? (
          <img src={song.image_url} alt="" className="w-10 h-10 rounded object-cover shrink-0" />
        ) : (
          <div className="w-10 h-10 rounded bg-zinc-800 flex items-center justify-center shrink-0">
            <Music className="w-4 h-4 text-zinc-600" />
          </div>
        )}

        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium truncate ${active ? 'text-brand' : 'text-white'}`}>{song.title}</p>
          <p className="text-xs text-zinc-500 truncate">{song.artist}</p>
        </div>

        <span className="hidden sm:inline text-xs text-zinc-500 w-16 text-right shrink-0">{song.listening_count || 0} plays</span>
        <span className="hidden md:inline text-xs text-zinc-500 w-20 text-right shrink-0">{formatDate(song.last_listened_at)}</span>
        {song.top_tag && (
          <span className="hidden lg:inline text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-brand max-w-24 truncate shrink-0">
            {song.top_tag}
          </span>
        )}

        <div className="hidden group-hover:flex items-center gap-1 shrink-0">
          {QUICK_FEEDBACK.map(({ action, icon: Icon, tip }) => (
            <button
              key={action}
              type="button"
              title={tip}
              onClick={() => sendFeedback(action)}
              className={`w-6 h-6 rounded flex items-center justify-center ${feedback === action ? 'text-brand' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              <Icon className="w-3 h-3" />
            </button>
          ))}
        </div>

        {song.spotify_id && (
          <a
            href={`https://open.spotify.com/track/${song.spotify_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-zinc-600 hover:text-brand shrink-0"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
      </div>
    </div>
  )
}

export default function Songs() {
  const [songs, setSongs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sort, setSort] = useState('recent')
  const [view, setView] = useState('grid')
  const [selected, setSelected] = useState(null)
  const [containerRef, size] = useElementSize()

  useEffect(() => {
    setLoading(true)
    const params = { limit: 5000 }
    if (statusFilter) params.enrichment_status = statusFilter
    api.get('/songs', params)
      .then(setSongs)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [statusFilter])

  const filtered = useMemo(() => {
    let list = songs
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(s =>
        s.title?.toLowerCase().includes(q) ||
        s.artist?.toLowerCase().includes(q) ||
        s.genre?.toLowerCase().includes(q) ||
        s.top_tag?.toLowerCase().includes(q)
      )
    }
    return [...list].sort((a, b) => {
      switch (sort) {
        case 'plays': return (b.listening_count || 0) - (a.listening_count || 0)
        case 'popularity': return (b.popularity_score || 0) - (a.popularity_score || 0)
        case 'alpha': return (a.title || '').localeCompare(b.title || '')
        default: return (b.last_listened_at || '').localeCompare(a.last_listened_at || '')
      }
    })
  }, [songs, search, sort])

  const width = Math.max(320, size.width || 960)
  const columns = width >= 1280 ? 6 : width >= 1024 ? 5 : width >= 768 ? 4 : width >= 640 ? 3 : 2
  const columnWidth = Math.floor(width / columns)
  const rowHeight = columnWidth + 94
  const virtualHeight = Math.max(420, Math.min(900, window.innerHeight - 260))

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Songs</h1>
        <p className="text-zinc-400 text-sm mt-1">
          {loading ? 'Loading...' : `${filtered.length.toLocaleString()} songs`}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search songs, artists, genres..."
            className="w-full pl-9 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-brand"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="w-4 h-4 text-zinc-500" />
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="bg-zinc-800 border border-zinc-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:border-brand">
            {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={sort} onChange={e => setSort(e.target.value)} className="bg-zinc-800 border border-zinc-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:border-brand">
            {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <div className="flex gap-1 bg-zinc-800 rounded-lg p-1">
            <button type="button" title="Grid view" onClick={() => setView('grid')} className={`w-8 h-8 rounded-md flex items-center justify-center ${view === 'grid' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'}`}>
              <Grid3X3 className="w-4 h-4" />
            </button>
            <button type="button" title="List view" onClick={() => setView('list')} className={`w-8 h-8 rounded-md flex items-center justify-center ${view === 'list' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'}`}>
              <List className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Spinner size="lg" /></div>
      ) : error ? (
        <p className="text-red-400">{error}</p>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-zinc-500">
          {search ? 'No songs match your search.' : 'No songs yet - sync your Spotify history.'}
        </div>
      ) : (
        <div ref={containerRef} className="w-full">
          {view === 'grid' ? (
            <FixedSizeGrid
              columnCount={columns}
              columnWidth={columnWidth}
              height={virtualHeight}
              rowCount={Math.ceil(filtered.length / columns)}
              rowHeight={rowHeight}
              width={width}
            >
              {({ columnIndex, rowIndex, style }) => {
                const index = rowIndex * columns + columnIndex
                const song = filtered[index]
                if (!song) return null
                return (
                  <div style={style} className="p-2">
                    <SongCard song={song} onClick={() => setSelected(song)} />
                  </div>
                )
              }}
            </FixedSizeGrid>
          ) : (
            <FixedSizeList height={virtualHeight} itemCount={filtered.length} itemSize={72} width={width}>
              {({ index, style }) => <SongListRow song={filtered[index]} index={index} style={style} />}
            </FixedSizeList>
          )}
        </div>
      )}

      {selected && (
        <SongModal
          song={selected}
          onClose={() => setSelected(null)}
          onUpdate={updated => {
            setSongs(prev => prev.map(s => s.id === updated.id ? { ...s, ...updated } : s))
            setSelected(updated)
          }}
        />
      )}
    </div>
  )
}
