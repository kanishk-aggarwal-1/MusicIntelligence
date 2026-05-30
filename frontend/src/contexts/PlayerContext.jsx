import { createContext, useContext, useEffect, useRef, useState } from 'react'

const PlayerContext = createContext(null)

export function PlayerProvider({ children }) {
  const [current, setCurrent] = useState(null)   // { title, artist, image_url, preview_url }
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)    // 0–1
  const audioRef = useRef(new Audio())
  // Refs so keyboard handler never closes over stale state
  const playingRef = useRef(false)
  const currentRef = useRef(null)

  useEffect(() => { playingRef.current = playing }, [playing])
  useEffect(() => { currentRef.current = current }, [current])

  useEffect(() => {
    const audio = audioRef.current
    const onTime = () => setProgress(audio.duration ? audio.currentTime / audio.duration : 0)
    const onEnded = () => { setPlaying(false); setProgress(0) }
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('ended', onEnded)
    }
  }, [])

  // Global keyboard shortcuts — only active when a song is loaded
  useEffect(() => {
    function onKey(e) {
      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (document.activeElement?.isContentEditable) return
      if (!currentRef.current) return

      const audio = audioRef.current

      if (e.code === 'Space') {
        e.preventDefault()
        if (playingRef.current) { audio.pause(); setPlaying(false) }
        else { audio.play().catch(() => {}); setPlaying(true) }
      }
      if (e.code === 'ArrowRight' && audio.duration) {
        e.preventDefault()
        audio.currentTime = Math.min(audio.duration, audio.currentTime + 10)
      }
      if (e.code === 'ArrowLeft' && audio.duration) {
        e.preventDefault()
        audio.currentTime = Math.max(0, audio.currentTime - 10)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, []) // empty — reads from refs

  function play(song) {
    const audio = audioRef.current
    if (!song.preview_url) return
    if (current?.preview_url === song.preview_url) {
      playing ? audio.pause() : audio.play()
      setPlaying(!playing)
      return
    }
    audio.pause()
    audio.src = song.preview_url
    audio.play()
    setCurrent(song)
    setPlaying(true)
    setProgress(0)
  }

  function stop() {
    audioRef.current.pause()
    setPlaying(false)
  }

  function seek(ratio) {
    const audio = audioRef.current
    if (audio.duration) audio.currentTime = ratio * audio.duration
  }

  const isPlaying = (song) => playing && current?.preview_url === song?.preview_url

  return (
    <PlayerContext.Provider value={{ current, playing, progress, play, stop, seek, isPlaying }}>
      {children}
    </PlayerContext.Provider>
  )
}

export const usePlayer = () => useContext(PlayerContext)
