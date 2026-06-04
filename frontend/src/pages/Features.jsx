import { useState, useEffect, useRef, useCallback } from 'react'
import { RefreshCw, Trash2, BarChart2, Upload } from 'lucide-react'
import { api } from '../lib/api'
import Spinner from '../components/ui/Spinner'

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

function Result({ data }) {
  if (!data) return null
  return (
    <pre className="text-xs bg-zinc-950 rounded-lg p-3 text-zinc-300 overflow-auto max-h-48">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

// Keys shown in the summary grid, tailored per job type.
const JOB_RESULT_KEYS = {
  import_history:    ['new_history_rows', 'new_songs', 'valid_tracks'],
  backfill_metadata: ['processed', 'total_candidates', 'scanned', 'updated'],
}
const RESULT_KEY_LABELS = {
  new_history_rows: 'history rows added',
  new_songs:        'new songs',
  valid_tracks:     'tracks in file',
  processed:        'processed',
  total_candidates: 'candidates',
  scanned:          'scanned',
  updated:          'updated',
}

function JobProgress({ job, onRetry }) {
  if (!job) return null
  const failed = job.status === 'failed'
  const done = ['succeeded', 'failed', 'cancelled'].includes(job.status)
  const total = Number(job.progress_total || 0)
  const current = Number(job.progress_current || 0)
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
  const result = job.result || null
  const resultKeys = JOB_RESULT_KEYS[job.job_type] || ['scanned', 'updated', 'new_songs']

  return (
    <div className={`rounded-lg border p-3 space-y-2 ${failed ? 'bg-red-950/20 border-red-900/50' : 'bg-zinc-950 border-zinc-800'}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-white text-sm capitalize">{job.status}</p>
          <p className={failed ? 'text-red-300 text-xs mt-0.5 line-clamp-2' : 'text-zinc-500 text-xs mt-0.5 line-clamp-2'}>
            {failed ? (job.error || job.message || 'Job failed') : (job.message || 'Working…')}
          </p>
        </div>
        {failed && (
          <button
            type="button"
            onClick={onRetry}
            className="text-xs text-red-200 hover:text-white underline underline-offset-2 shrink-0"
          >
            Retry
          </button>
        )}
      </div>
      {(total > 0 || !done) && (
        <>
          <div className="h-2.5 bg-zinc-800 rounded-full overflow-hidden">
            {pct === 0 && !done ? (
              <div className="h-full w-1/3 rounded-full bg-brand/60 animate-pulse" />
            ) : (
              <div
                className={`h-full rounded-full transition-all duration-700 ${failed ? 'bg-red-400' : 'bg-brand'}`}
                style={{ width: `${Math.max(pct, done ? 0 : 2)}%` }}
              />
            )}
          </div>
          {!done && (
            <p className="text-zinc-300 text-sm font-medium tabular-nums">
              {total > 1
                ? `${current.toLocaleString()} / ${total.toLocaleString()} tracks`
                : job?.message || 'Working…'}
            </p>
          )}
        </>
      )}
      {done && result && (
        <div className="grid grid-cols-3 gap-2 pt-1">
          {resultKeys.map(key => result[key] !== undefined && (
            <div key={key} className="bg-zinc-900 rounded-md p-2">
              <p className="text-zinc-500 text-[11px]">{RESULT_KEY_LABELS[key] || key.replace(/_/g, ' ')}</p>
              <p className="text-white text-sm font-semibold">{Number(result[key]).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ActionButton({ onClick, loading, icon: Icon, label, variant = 'default' }) {
  const base = 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60'
  const variants = {
    default:  'bg-zinc-800 text-white hover:bg-zinc-700',
    primary:  'bg-brand text-black hover:bg-green-400',
    danger:   'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20',
  }
  return (
    <button onClick={onClick} disabled={loading} className={`${base} ${variants[variant]}`}>
      {loading ? <Spinner size="sm" /> : <Icon className="w-4 h-4" />}
      {label}
    </button>
  )
}

function ImportSection() {
  const [job, setJob]           = useState(null)
  const [loading, setLoading]   = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [error, setError]       = useState(null)
  const fileRef = useRef(null)
  const pollFailuresRef = useRef(0)

  useEffect(() => {
    const storedJobId = localStorage.getItem('musicintel:import-job-id')
    if (!storedJobId) return
    api.get(`/jobs/${storedJobId}`)
      .then(existing => {
        if (['succeeded', 'failed', 'cancelled'].includes(existing.status)) {
          localStorage.removeItem('musicintel:import-job-id')
          return
        }
        setJob(existing)
      })
      .catch(() => localStorage.removeItem('musicintel:import-job-id'))
  }, [])

  // Poll job until done — 800 ms so the "X / Y tracks" counter visibly counts up
  useEffect(() => {
    if (!job?.id || ['succeeded', 'failed', 'cancelled'].includes(job.status)) return
    const t = setInterval(async () => {
      try {
        const updated = await api.get(`/jobs/${job.id}`)
        pollFailuresRef.current = 0
        setJob(updated)
        if (['succeeded', 'failed', 'cancelled'].includes(updated.status)) {
          localStorage.removeItem('musicintel:import-job-id')
          clearInterval(t)
        }
      } catch (e) {
        pollFailuresRef.current += 1
        const transient = e?.status >= 500 || /bad gateway|failed to fetch|network/i.test(e?.message || '')
        setJob(prev => prev ? {
          ...prev,
          message: transient
            ? 'Backend is restarting. Still checking job status...'
            : 'Lost connection while checking job status',
          error: transient ? null : e.message,
        } : prev)
        if (!transient || pollFailuresRef.current >= 40) clearInterval(t)
      }
    }, 800)
    return () => clearInterval(t)
  }, [job?.id, job?.status])

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setLoadingMsg('Reading file…')
    setError(null)
    setJob(null)
    localStorage.removeItem('musicintel:import-job-id')
    try {
      // Parse and pre-process the file entirely in the browser before sending.
      //
      // Spotify's extended history has ~25 fields per entry but the backend
      // only needs 6, and many entries (podcasts, <30 s plays) are discarded.
      // Doing this client-side reduces a typical 12 MB file to ~1 MB and lets
      // us send plain JSON instead of multipart — avoiding the Render proxy
      // body-size limit that was dropping the connection at ~4 MB.
      const raw = await file.text()
      let parsed
      try {
        parsed = JSON.parse(raw)
      } catch {
        throw new Error('Could not parse file — make sure it is a Spotify history JSON file.')
      }
      if (!Array.isArray(parsed)) {
        throw new Error('Unexpected file format — expected a JSON array.')
      }

      setLoadingMsg('Processing…')

      // Mirror backend _parse_extended_history logic exactly
      const tracks = parsed
        .filter(e =>
          !e.episode_name &&
          e.master_metadata_track_name &&
          (e.ms_played || 0) >= 30_000
        )
        .map(e => {
          const uri = e.spotify_track_uri || ''
          const reason = (e.reason_end || '').toLowerCase()
          return {
            title:      e.master_metadata_track_name,
            artist:     e.master_metadata_album_artist_name || '',
            spotify_id: uri.startsWith('spotify:track:') ? uri.split(':').pop() : null,
            played_at:  e.ts || null,
            ms_played:  e.ms_played || 0,
            skipped:    reason === 'fwdbtn' || reason === 'endplay',
          }
        })

      if (tracks.length === 0) {
        throw new Error('No playable tracks found in this file. Make sure it is a StreamingHistory_music_*.json file.')
      }

      setLoadingMsg(`Uploading ${tracks.length.toLocaleString()} tracks…`)

      // Send as application/json — no multipart overhead, ~1 MB instead of ~12 MB
      const result = await api.post('/user/import-history/job', tracks)
      setJob(result)
      localStorage.setItem('musicintel:import-job-id', result.id)
      window.dispatchEvent(new CustomEvent('musicintel:job-started', { detail: { job: result } }))
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setLoading(false)
      setLoadingMsg('')
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="space-y-4">
      <ol className="space-y-1.5 text-sm text-zinc-400 list-decimal list-inside marker:text-zinc-600">
        <li>Go to <a href="https://www.spotify.com/account/privacy/" target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">spotify.com/account/privacy</a> → <strong className="text-zinc-300">Request data</strong></li>
        <li>Wait for the email (up to 30 days), then download and unzip the file</li>
        <li>Upload any <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded">StreamingHistory_music_*.json</code> file below — repeat for each file</li>
      </ol>

      <div className="flex items-center gap-3 flex-wrap">
        <label className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${loading ? 'bg-zinc-700 text-zinc-500 cursor-not-allowed' : 'bg-brand text-black hover:bg-green-400'}`}>
          {loading ? <Spinner size="sm" /> : <Upload className="w-4 h-4" />}
          {loading ? (loadingMsg || 'Working…') : 'Choose JSON file'}
          <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={handleFile} disabled={loading} />
        </label>
        {job?.status === 'succeeded' && (
          <span className="text-green-400 text-sm">
            ✓ Imported {job.result?.valid_tracks?.toLocaleString() ?? '?'} tracks
          </span>
        )}
      </div>

      {job?.status === 'succeeded' && (
        <div className="bg-zinc-950 border border-zinc-700 rounded-lg px-4 py-3 space-y-1.5">
          <p className="text-zinc-300 text-sm font-medium">Import complete ✓</p>
          <p className="text-zinc-400 text-xs">
            Upload any remaining Spotify history files above, then follow these steps in order:
          </p>
          <ol className="text-xs text-zinc-400 list-decimal list-inside space-y-1 marker:text-zinc-600">
            <li><span className="text-zinc-300">Deduplication</span> — merge duplicate tracks below</li>
            <li><span className="text-zinc-300">Metadata Enrichment</span> — fetch Last.fm tags &amp; genres below</li>
          </ol>
        </div>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}
      <JobProgress job={job} onRetry={() => fileRef.current?.click()} />
    </div>
  )
}

const ENRICH_BATCH = 2000   // songs per job — large enough to make progress,
                             // small enough that a Render restart loses < 2 k

export default function Features() {
  const [backfillResult, setBackfillResult]     = useState(null)
  const [backfillLoading, setBackfillLoading]   = useState(false)
  const [backfillPoll, setBackfillPoll]         = useState(null)
  const [retryFailed, setRetryFailed]           = useState(false)
  const [retryPartial, setRetryPartial]         = useState(false)
  const [pendingCount, setPendingCount]         = useState(null)
  const [enrichedSoFar, setEnrichedSoFar]       = useState(0)
  const [autoEnrich, setAutoEnrich]             = useState(false)

  const [qualityResult, setQualityResult] = useState(null)
  const [qualityLoading, setQualityLoading] = useState(false)

  const [dedupPreview, setDedupPreview] = useState(null)
  const [dedupLoading, setDedupLoading] = useState(false)
  const [dedupApplying, setDedupApplying] = useState(false)
  const [dedupResult, setDedupResult] = useState(null)

  const [cacheClearing, setCacheClearing] = useState(false)
  const [cacheResult, setCacheResult] = useState(null)

  // Fetch pending count once on mount so the button label is informative
  useEffect(() => {
    api.get('/user/sync-status')
      .then(s => setPendingCount(s.pending_enrichment_count ?? null))
      .catch(() => {})
  }, [])

  // Poll the active backfill job; auto-restart if autoEnrich is on and more remain
  useEffect(() => {
    if (!backfillResult?.id || ['succeeded', 'failed', 'cancelled'].includes(backfillResult.status)) return

    const timer = setInterval(async () => {
      try {
        const job = await api.get(`/jobs/${backfillResult.id}`)
        setBackfillResult(job)
        if (['succeeded', 'failed', 'cancelled'].includes(job.status)) {
          clearInterval(timer)
          setBackfillPoll(null)

          if (job.status === 'succeeded') {
            const processed = job.result?.total_candidates ?? 0
            setEnrichedSoFar(prev => prev + processed)

            // Re-fetch pending count so the label stays accurate
            api.get('/user/sync-status')
              .then(s => {
                const remaining = s.pending_enrichment_count ?? 0
                setPendingCount(remaining)
                // Auto-continue if there are still songs to enrich
                if (autoEnrich && remaining > 0) {
                  startBatch(remaining)
                } else {
                  setAutoEnrich(false)
                }
              })
              .catch(() => setAutoEnrich(false))
          } else {
            setAutoEnrich(false)
          }
        }
      } catch (e) {
        setBackfillPoll({ error: e.message })
      }
    }, 1500)

    setBackfillPoll({ active: true })
    return () => clearInterval(timer)
  }, [backfillResult?.id, backfillResult?.status, autoEnrich, startBatch])

  const startBatch = useCallback(async (overrideLimit) => {
    setBackfillLoading(true)
    setBackfillPoll(null)
    const limit = Math.min(overrideLimit ?? pendingCount ?? ENRICH_BATCH, ENRICH_BATCH)
    try {
      const job = await api.post(
        `/user/backfill-metadata/job?limit=${limit}&retry_partial=${retryPartial}&retry_failed=${retryFailed}`
      )
      setBackfillResult(job)
    } catch (e) {
      setBackfillResult({ error: e.message })
      setAutoEnrich(false)
    } finally {
      setBackfillLoading(false)
    }
  }, [pendingCount, retryPartial, retryFailed])

  async function handleBackfill() {
    setEnrichedSoFar(0)
    setAutoEnrich(true)   // enable auto-restart for subsequent batches
    await startBatch(pendingCount)
  }

  async function handleQuality() {
    setQualityLoading(true)
    try {
      const res = await api.get('/insights/data-quality')
      setQualityResult(res)
    } catch (e) {
      setQualityResult({ error: e.message })
    } finally {
      setQualityLoading(false)
    }
  }

  async function handleDedupPreview() {
    setDedupLoading(true)
    try {
      const res = await api.get('/insights/dedup-preview')
      setDedupPreview(res)
    } catch (e) {
      setDedupPreview({ error: e.message })
    } finally {
      setDedupLoading(false)
    }
  }

  async function handleDedupApply() {
    setDedupApplying(true)
    try {
      const res = await api.post('/insights/dedup-apply')
      setDedupResult(res)
      setDedupPreview(null)
    } catch (e) {
      setDedupResult({ error: e.message })
    } finally {
      setDedupApplying(false)
    }
  }

  async function handleClearCache() {
    setCacheClearing(true)
    try {
      const res = await api.post('/insights/cache/clear?provider=lastfm')
      setCacheResult(res)
    } catch (e) {
      setCacheResult({ error: e.message })
    } finally {
      setCacheClearing(false)
    }
  }

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Library Tools</h1>
        <p className="text-zinc-400 text-sm mt-1">Enrichment, deduplication, and maintenance</p>
      </div>

      <Section
        title="Import Spotify History"
        description="Bootstrap your library instantly using Spotify's full data export — includes years of listening history, not just the last 50 tracks."
      >
        <ImportSection />
      </Section>

      <Section
        title="Metadata Enrichment"
        description="Fetch Last.fm tags and genre data for songs in your library."
      >
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input type="checkbox" checked={retryPartial} onChange={e => setRetryPartial(e.target.checked)} className="accent-brand" />
            Retry partial
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input type="checkbox" checked={retryFailed} onChange={e => setRetryFailed(e.target.checked)} className="accent-brand" />
            Retry failed
          </label>
          <ActionButton
            onClick={handleBackfill}
            loading={backfillLoading}
            icon={RefreshCw}
            label={
              pendingCount > 0
                ? `Enrich ${pendingCount.toLocaleString()} songs`
                : 'Run Enrichment'
            }
            variant="primary"
          />
        </div>

        {/* Overall multi-batch progress */}
        {autoEnrich && (pendingCount ?? 0) > 0 && (
          <p className="text-zinc-400 text-xs">
            Auto-running in {ENRICH_BATCH.toLocaleString()}-song batches
            {enrichedSoFar > 0 && ` · ${enrichedSoFar.toLocaleString()} enriched so far`}
            {pendingCount > 0 && ` · ${pendingCount.toLocaleString()} remaining`}
          </p>
        )}

        <JobProgress job={backfillResult} onRetry={handleBackfill} />
        {backfillPoll?.error && <p className="text-red-400 text-sm">{backfillPoll.error}</p>}
      </Section>

      <Section title="Data Quality" description="Check enrichment coverage across your library.">
        <ActionButton onClick={handleQuality} loading={qualityLoading} icon={BarChart2} label="Check Coverage" />
        {qualityResult && !qualityResult.error && (
          <div className="grid grid-cols-2 gap-3">
            {(qualityResult.coverage || []).map(c => (
              <div key={c.metric} className="bg-zinc-950 rounded-lg p-3">
                <p className="text-xs text-zinc-500">{c.metric}</p>
                <p className="text-white font-semibold">{c.percent}%</p>
                <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-brand rounded-full" style={{ width: `${c.percent}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
        {qualityResult?.error && <p className="text-red-400 text-sm">{qualityResult.error}</p>}
      </Section>

      <Section title="Deduplication" description="Find and merge duplicate songs in your library.">
        <div className="flex gap-2 flex-wrap">
          <ActionButton onClick={handleDedupPreview} loading={dedupLoading} icon={BarChart2} label="Preview Duplicates" />
          {dedupPreview?.duplicate_groups?.length > 0 && (
            <ActionButton onClick={handleDedupApply} loading={dedupApplying} icon={Trash2} label={`Merge ${dedupPreview.duplicate_groups.length} groups`} variant="danger" />
          )}
        </div>
        {dedupPreview && !dedupPreview.error && (
          <p className="text-zinc-400 text-sm">Found {dedupPreview.duplicate_groups?.length ?? 0} duplicate groups</p>
        )}
        <Result data={dedupResult} />
      </Section>

      <Section title="Cache" description="Clear the Last.fm API response cache to force fresh enrichment.">
        <ActionButton onClick={handleClearCache} loading={cacheClearing} icon={Trash2} label="Clear Last.fm Cache" variant="danger" />
        <Result data={cacheResult} />
      </Section>
    </div>
  )
}
