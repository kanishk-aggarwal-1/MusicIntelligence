import { Play, Pause, Music } from 'lucide-react'
import { usePlayer } from '../../contexts/PlayerContext'

export default function SongCard({ song, onClick }) {
  const { play, isPlaying } = usePlayer()
  const active = isPlaying(song)

  function handlePreview(e) {
    e.stopPropagation()
    play(song)
  }

  return (
    <div
      onClick={onClick}
      className="bg-zinc-900 rounded-xl overflow-hidden group cursor-pointer hover:bg-zinc-800 transition-colors"
    >
      {/* Album art */}
      <div className="relative aspect-square bg-zinc-800">
        {song.image_url ? (
          <img
            src={song.image_url}
            alt={song.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <Music className="w-10 h-10 text-zinc-600" />
          </div>
        )}

        {/* Preview button overlay */}
        {song.preview_url && (
          <button
            onClick={handlePreview}
            className={`absolute inset-0 flex items-center justify-center bg-black/50 transition-opacity ${
              active ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
            }`}
          >
            <div className={`w-12 h-12 rounded-full flex items-center justify-center bg-brand shadow-lg`}>
              {active ? (
                <Pause className="w-5 h-5 text-black fill-black" />
              ) : (
                <Play className="w-5 h-5 text-black fill-black ml-0.5" />
              )}
            </div>
          </button>
        )}

        {active && (
          <div className="absolute bottom-2 left-2 flex gap-0.5 items-end h-4">
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="w-1 bg-brand rounded-full animate-bounce"
                style={{ height: `${40 + i * 20}%`, animationDelay: `${i * 0.1}s` }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3">
        <p className="text-white text-sm font-medium truncate">{song.title}</p>
        <p className="text-zinc-400 text-xs truncate mt-0.5">{song.artist}</p>
        {(song.top_tag || song.genre) && (
          <span className="inline-block mt-1.5 text-xs px-2 py-0.5 bg-zinc-800 text-brand rounded-full truncate max-w-full">
            {song.top_tag || song.genre}
          </span>
        )}
      </div>
    </div>
  )
}
