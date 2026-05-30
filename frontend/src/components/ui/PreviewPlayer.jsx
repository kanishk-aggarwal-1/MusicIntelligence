import { Play, Pause, X, Music } from 'lucide-react'
import { usePlayer } from '../../contexts/PlayerContext'

export default function PreviewPlayer() {
  const { current, playing, progress, play, stop, seek } = usePlayer()

  if (!current) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900/95 backdrop-blur border-t border-zinc-800 px-4 py-3">
      <div className="max-w-screen-xl mx-auto flex items-center gap-4">

        {/* Art + info */}
        <div className="flex items-center gap-3 w-56 shrink-0">
          {current.image_url ? (
            <img src={current.image_url} alt="" className="w-10 h-10 rounded object-cover" />
          ) : (
            <div className="w-10 h-10 rounded bg-zinc-800 flex items-center justify-center">
              <Music className="w-5 h-5 text-zinc-500" />
            </div>
          )}
          <div className="min-w-0">
            <p className="text-white text-sm font-medium truncate">{current.title}</p>
            <p className="text-zinc-400 text-xs truncate">{current.artist}</p>
          </div>
        </div>

        {/* Controls + progress */}
        <div className="flex-1 flex flex-col gap-1.5">
          <div className="flex items-center justify-center">
            <button
              onClick={() => play(current)}
              className="w-8 h-8 rounded-full bg-white flex items-center justify-center hover:scale-105 transition-transform"
            >
              {playing ? (
                <Pause className="w-3.5 h-3.5 text-black fill-black" />
              ) : (
                <Play className="w-3.5 h-3.5 text-black fill-black ml-0.5" />
              )}
            </button>
          </div>
          <div
            className="w-full h-1 bg-zinc-700 rounded-full cursor-pointer"
            onClick={e => {
              const rect = e.currentTarget.getBoundingClientRect()
              seek((e.clientX - rect.left) / rect.width)
            }}
          >
            <div
              className="h-full bg-brand rounded-full transition-all"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <p className="text-center text-zinc-600 text-xs">
            <kbd className="font-mono">space</kbd> play/pause &nbsp;·&nbsp;
            <kbd className="font-mono">←→</kbd> seek 10s
          </p>
        </div>

        {/* Close */}
        <button onClick={stop} className="p-1.5 text-zinc-500 hover:text-white transition-colors shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
