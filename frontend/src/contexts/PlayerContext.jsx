import { createContext, useContext, useEffect, useRef, useState } from 'react'

const PlayerContext = createContext(null)

export function PlayerProvider({ children }) {
  const [current, setCurrent] = useState(null)   // { title, artist, image_url, preview_url }
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)    // 0–1
  const audioRef = useRef(new Audio())

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
