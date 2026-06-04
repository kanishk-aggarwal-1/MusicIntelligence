import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Music2, ListMusic, Tag, Heart, Wrench, Settings, LogOut, RefreshCw, CheckCircle, XCircle, Search, Activity } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useSyncFlow } from '../../hooks/useSyncFlow'

const links = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/songs',     icon: Music2,          label: 'Songs'     },
  { to: '/browse',    icon: Tag,             label: 'Browse'    },
  { to: '/for-you',   icon: Heart,           label: 'For You'   },
  { to: '/playlists', icon: ListMusic,        label: 'Playlists' },
  { to: '/features',  icon: Wrench,           label: 'Tools'     },
  { to: '/stats',     icon: Activity,         label: 'Stats'     },
  { to: '/settings',  icon: Settings,         label: 'Settings'  },
]

function formatUserId(id) {
  if (!id) return ''
  // Strip spotify:user: prefix if present, replace underscores/dashes, capitalise
  return id.replace(/^spotify:user:/i, '').replace(/[_-]/g, ' ')
}

function formatAgo(value) {
  if (!value) return null
  const diff = Date.now() - new Date(value).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`
  return `${Math.round(diff / 86_400_000)}d ago`
}

function statusText(status) {
  if (!status) return 'Checking freshness'
  if (!status.total_songs) return 'No library synced'
  const pending = Number(status.pending_enrichment_count || 0)
  if (pending > 0) {
    const synced = formatAgo(status.last_synced_at)
    return `${synced ? `Synced ${synced}` : 'Synced'} - ${pending} pending`
  }
  return 'Up to date'
}

function JobToast({ job, label, onRetry }) {
  if (!job) return null
  const failed = job.status === 'failed'
  const detail = failed ? (job.error || job.message || 'Job failed') : job.message
  return (
    <div className={`mx-1 px-3 py-2 rounded-lg border text-xs space-y-1.5 ${failed ? 'bg-red-950/30 border-red-900/60' : 'bg-zinc-800 border-zinc-700'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-zinc-300 truncate">{label || job.job_type?.replace(/_/g, ' ')}</span>
        {job.status === 'succeeded' && <CheckCircle className="w-3.5 h-3.5 text-green-400 shrink-0" />}
        {job.status === 'failed'    && <XCircle    className="w-3.5 h-3.5 text-red-400 shrink-0"   />}
      </div>
      {job.progress_total > 0 && (
        <div className="h-1 bg-zinc-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-brand rounded-full transition-all"
            style={{ width: `${Math.min(100, ((job.progress_current || 0) / job.progress_total) * 100)}%` }}
          />
        </div>
      )}
      <p className={failed ? 'text-red-300 line-clamp-2' : 'text-zinc-500 truncate'}>{detail}</p>
      {failed && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-red-200 hover:text-white underline underline-offset-2"
        >
          Retry
        </button>
      )}
    </div>
  )
}

export default function Sidebar({ onNavigate }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { syncing, syncJob, enrichmentJob, importJob, syncStatus, syncAtLimit, startSync, startEnrichment } = useSyncFlow()

  async function handleSync() {
    try {
      await startSync()
    } catch (e) {
      console.error(e)
    }
  }

  async function handleEnrichmentRetry() {
    try {
      await startEnrichment()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <aside className="w-56 shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-brand flex items-center justify-center text-black text-sm">♪</div>
          <div className="min-w-0">
            <span className="font-semibold text-white">MusicIntel</span>
            {syncStatus?.total_songs > 0 && (
              <p className="text-zinc-600 text-xs leading-tight">
                {syncStatus.total_songs.toLocaleString()} songs
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Search trigger */}
      <div className="px-3 py-2 border-b border-zinc-800">
        <button
          type="button"
          onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }))}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800 text-zinc-500 text-sm hover:text-zinc-300 transition-colors text-left"
        >
          <Search className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1">Search</span>
          <kbd className="font-mono text-xs bg-zinc-700 px-1.5 py-0.5 rounded">⌘K</kbd>
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-brand/10 text-brand font-medium'
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
              }`
            }
          >
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Bottom: user + actions */}
      <div className="px-3 py-4 border-t border-zinc-800 space-y-1">
        <button
          onClick={handleSync}
          disabled={syncing}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing…' : 'Sync Now'}
        </button>

        <button
          type="button"
          onClick={() => { navigate('/features'); onNavigate?.() }}
          className="w-full px-3 py-1.5 text-left text-xs text-zinc-500 hover:text-zinc-300"
        >
          {statusText(syncStatus)}
        </button>

        <div className="space-y-2">
          <JobToast job={syncJob} label="Syncing history" onRetry={handleSync} />
          <JobToast job={importJob} label="Importing history" />
          <JobToast job={enrichmentJob} label="Enriching tags" onRetry={handleEnrichmentRetry} />
          {syncAtLimit && !syncJob && (
            <p className="mx-1 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-xs text-zinc-400 leading-snug">
              Spotify limits recent history to 50 tracks. Sync regularly to grow your library.
            </p>
          )}
        </div>

        {user && (
          <div className="px-3 py-2">
            <p className="text-xs text-zinc-500 truncate capitalize" title={user.user_id}>
              {formatUserId(user.user_id)}
            </p>
          </div>
        )}

        <button
          onClick={logout}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-zinc-400 hover:text-red-400 hover:bg-zinc-800 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Log out
        </button>
      </div>
    </aside>
  )
}
