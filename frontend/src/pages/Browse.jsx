import { useState, useEffect } from 'react'
import { Play, Pause, Music, Tag, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { usePlayer } from '../contexts/PlayerContext'
import Spinner from '../components/ui/Spinner'
import ErrorBoundary from '../components/ui/ErrorBoundary'

function SongRow({ song, index }) {
  const { play, isPlaying } = usePlayer()
  const active = isPlaying(song)

  return (
    <div
      className={`flex items-center gap-3 px-3 py-2 rounded-lg group transition-colors ${
        active ? 'bg-brand/10' : 'hover:bg-zinc-800'
      }`}
    >
      <span className="w-5 text-xs text-zinc-600 text-center shrink-0 group-hover:hidden">{index + 1}</span>
      <button
        onClick={() => song.preview_url && play(song)}
        className="w-5 hidden group-hover:flex items-center justify-center shrink-0"
        disabled={!song.preview_url}
      >
        {active
          ? <Pause className="w-3.5 h-3.5 text-brand" />
          : <Play className={`w-3.5 h-3.5 ${song.preview_url ? 'text-zinc-300' : 'text-zinc-600'}`} />}
      </button>

      {song.image_url ? (
        <img src={song.image_url} alt="" className="w-9 h-9 rounded object-cover shrink-0" />
      ) : (
        <div className="w-9 h-9 rounded bg-zinc-800 flex items-center justify-center shrink-0">
          <Music className="w-3.5 h-3.5 text-zinc-600" />
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className={`text-sm truncate ${active ? 'text-brand font-medium' : 'text-white'}`}>{song.title}</p>
        <p className="text-xs text-zinc-500 truncate">{song.artist}</p>
      </div>

      {song.popularity_score != null && (
        <span className="text-xs text-zinc-600 shrink-0">{song.popularity_score.toFixed(1)}</span>
      )}
    </div>
  )
}

function TagList({ tags, selected, onSelect }) {
  if (!tags.length) return (
    <p className="text-zinc-500 text-sm px-1">No tags yet - enrich your library in Features to unlock tag browsing.</p>
  )

  return (
    <div className="space-y-0.5 md:space-y-0 flex md:block gap-2 overflow-x-auto md:overflow-visible pb-1 md:pb-0">
      {tags.map(t => (
        <button
          key={t.name}
          onClick={() => onSelect(t.name)}
          className={`md:w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors text-left shrink-0 md:shrink ${
            selected === t.name
              ? 'bg-brand/10 text-brand font-medium'
              : 'text-zinc-300 hover:bg-zinc-800 hover:text-white'
          }`}
        >
          <span className="truncate flex-1">{t.name}</span>
          <span className={`text-xs ml-2 shrink-0 ${selected === t.name ? 'text-brand/70' : 'text-zinc-600'}`}>
            {t.song_count}
          </span>
        </button>
      ))}
    </div>
  )
}

function SongPanel({ tag }) {
  const [songs, setSongs] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!tag) { setSongs([]); return }
    setLoading(true)
    api.get(`/insights/tags/${encodeURIComponent(tag)}/songs`, { limit: 50 })
      .then(d => setSongs(d.songs || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [tag])

  if (!tag) return (
    <div className="flex flex-col items-center justify-center h-full text-zinc-600 gap-2">
      <Tag className="w-10 h-10" />
      <p className="text-sm">Select a tag to see songs</p>
    </div>
  )

  if (loading) return (
    <div className="flex items-center justify-center h-full"><Spinner /></div>
  )

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-zinc-800 shrink-0">
        <h2 className="text-white font-semibold capitalize">{tag}</h2>
        <p className="text-zinc-500 text-xs mt-0.5">{songs.length} song{songs.length !== 1 ? 's' : ''}</p>
      </div>
      {songs.length === 0 ? (
        <p className="text-zinc-500 text-sm p-4">No songs found for this tag.</p>
      ) : (
        <div className="overflow-y-auto flex-1 p-2 space-y-0.5">
          {songs.map((song, i) => (
            <SongRow key={song.id} song={song} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function Browse() {
  const [tags, setTags] = useState([])
  const [tagsLoading, setTagsLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.get('/insights/tags', { limit: 200 })
      .then(d => setTags(d.tags || []))
      .catch(console.error)
      .finally(() => setTagsLoading(false))
  }, [])

  const filtered = search.trim()
    ? tags.filter(t => t.name.toLowerCase().includes(search.toLowerCase()))
    : tags

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-3.5rem)] md:h-screen overflow-hidden">
      {/* Tag sidebar */}
      <div className="md:w-56 shrink-0 border-b md:border-b-0 md:border-r border-zinc-800 flex flex-col max-h-48 md:max-h-none">
        <div className="px-4 py-4 border-b border-zinc-800 shrink-0">
          <h1 className="text-white font-semibold text-sm">Browse by Tag</h1>
          <input
            type="text"
            placeholder="Filter tags…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="mt-2 w-full bg-zinc-800 border border-zinc-700 text-white text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-brand placeholder-zinc-600"
          />
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {tagsLoading
            ? <div className="flex justify-center py-6"><Spinner size="sm" /></div>
            : <TagList tags={filtered} selected={selected} onSelect={setSelected} />}
        </div>
      </div>

      {/* Song panel */}
      <div className="flex-1 min-w-0 bg-zinc-950">
        <ErrorBoundary><SongPanel tag={selected} /></ErrorBoundary>
      </div>
    </div>
  )
}
