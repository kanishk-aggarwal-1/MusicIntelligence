import { useState, useEffect } from 'react'
import { ExternalLink, LogOut, Trash2, User } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import Spinner from '../components/ui/Spinner'
import { SkeletonLine } from '../components/ui/Skeleton'
import { useNavigate } from 'react-router-dom'

function Section({ title, description, children }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800 space-y-4">
      <div>
        <h2 className="text-white font-semibold">{title}</h2>
        {description && <p className="text-zinc-400 text-sm mt-1">{description}</p>}
      </div>
      {children}
    </div>
  )
}

function ProfileSkeleton() {
  return (
    <div className="flex items-center gap-4 animate-pulse">
      <div className="w-16 h-16 rounded-full bg-zinc-800 shrink-0" />
      <div className="space-y-2">
        <SkeletonLine className="h-4 w-36" />
        <SkeletonLine className="h-3 w-24" />
        <SkeletonLine className="h-3 w-20" />
      </div>
    </div>
  )
}

export default function Settings() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [profile, setProfile]       = useState(null)
  const [profileLoading, setPL]     = useState(true)
  const [deleteConfirm, setDC]      = useState(false)
  const [deleting, setDeleting]     = useState(false)
  const [deleteError, setDeleteErr] = useState(null)

  useEffect(() => {
    api.get('/user/profile')
      .then(setProfile)
      .catch(console.error)
      .finally(() => setPL(false))
  }, [])

  async function handleDelete() {
    setDeleting(true)
    setDeleteErr(null)
    try {
      await api.delete('/user/delete-data')
      await logout()
      navigate('/login')
    } catch (e) {
      setDeleteErr(e.message || 'Delete failed. Please try again.')
      setDeleting(false)
      setDC(false)
    }
  }

  const avatar = profile?.images?.[0]?.url
  const planBadge = profile?.product === 'premium'
    ? <span className="text-xs px-2 py-0.5 rounded-full bg-brand/10 text-brand">Spotify Premium</span>
    : profile?.product
      ? <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 capitalize">{profile.product}</span>
      : null

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-zinc-400 text-sm mt-1">Your account and preferences</p>
      </div>

      {/* Spotify profile */}
      <Section title="Spotify Account" description="Your connected Spotify profile.">
        {profileLoading ? <ProfileSkeleton /> : profile ? (
          <div className="flex items-center gap-4">
            {avatar ? (
              <img src={avatar} alt="" className="w-16 h-16 rounded-full object-cover shrink-0" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-zinc-800 flex items-center justify-center shrink-0">
                <User className="w-7 h-7 text-zinc-500" />
              </div>
            )}
            <div className="min-w-0 space-y-1">
              <p className="text-white font-semibold truncate">{profile.display_name}</p>
              {profile.email && <p className="text-zinc-400 text-sm truncate">{profile.email}</p>}
              <div className="flex items-center gap-2 flex-wrap">
                {profile.followers > 0 && (
                  <span className="text-xs text-zinc-500">{profile.followers.toLocaleString()} followers</span>
                )}
                {profile.country && (
                  <span className="text-xs text-zinc-500">{profile.country}</span>
                )}
                {planBadge}
              </div>
              {profile.spotify_url && (
                <a
                  href={profile.spotify_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-brand hover:underline mt-1"
                >
                  Open Spotify profile <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        ) : (
          <p className="text-zinc-500 text-sm">Could not load Spotify profile.</p>
        )}
      </Section>

      {/* Session */}
      <Section title="Session" description="Log out of MusicIntelligence on this device.">
        <button
          onClick={async () => { await logout(); navigate('/login') }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Log out
        </button>
      </Section>

      {/* Danger zone */}
      <Section title="Delete My Data" description="Permanently remove all your listening history, playlists, goals, and session data. Songs and artists are shared and will not be deleted. This cannot be undone.">
        {!deleteConfirm ? (
          <button
            onClick={() => setDC(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Delete all my data
          </button>
        ) : (
          <div className="space-y-3 bg-red-950/20 border border-red-900/40 rounded-lg p-4">
            <p className="text-red-300 text-sm font-medium">
              This will permanently delete your listening history, playlists, goals, and log you out. Are you sure?
            </p>
            {deleteError && <p className="text-red-400 text-xs">{deleteError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-red-500 text-white font-medium hover:bg-red-400 disabled:opacity-60 transition-colors"
              >
                {deleting ? <Spinner size="sm" /> : <Trash2 className="w-4 h-4" />}
                {deleting ? 'Deleting…' : 'Yes, delete everything'}
              </button>
              <button
                onClick={() => setDC(false)}
                disabled={deleting}
                className="px-4 py-2 rounded-lg text-sm bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </Section>
    </div>
  )
}
