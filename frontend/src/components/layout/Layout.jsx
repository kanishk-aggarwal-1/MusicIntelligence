import Sidebar from './Sidebar'
import PreviewPlayer from '../ui/PreviewPlayer'
import { usePlayer } from '../../contexts/PlayerContext'
import { Menu, X } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useState } from 'react'

const PAGE_TITLES = {
  '/dashboard': 'Dashboard',
  '/songs': 'Songs',
  '/browse': 'Browse',
  '/playlists': 'Playlists',
  '/features': 'Features',
}

export default function Layout({ children }) {
  const { current } = usePlayer()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || 'Dashboard'

  return (
    <div className="flex min-h-screen">
      <div className="hidden md:block sticky top-0 h-screen">
        <Sidebar />
      </div>

      <div className="md:hidden fixed top-0 left-0 right-0 z-40 h-14 bg-zinc-950/95 backdrop-blur border-b border-zinc-800 flex items-center gap-3 px-3">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-zinc-300 hover:bg-zinc-800"
          aria-label="Open navigation"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="min-w-0">
          <p className="text-white text-sm font-semibold leading-tight">MusicIntel</p>
          <p className="text-zinc-500 text-xs leading-tight">{title}</p>
        </div>
      </div>

      {open && (
        <div className="md:hidden fixed inset-0 z-50">
          <button
            type="button"
            className="absolute inset-0 bg-black/60"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          />
          <div className="absolute inset-y-0 left-0 shadow-2xl">
            <div className="absolute top-3 right-3 z-10">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:bg-zinc-800"
                aria-label="Close navigation"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <Sidebar onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}

      <main className={`flex-1 overflow-auto pt-14 md:pt-0 ${current ? 'pb-24' : ''}`}>
        {children}
      </main>
      <PreviewPlayer />
    </div>
  )
}
