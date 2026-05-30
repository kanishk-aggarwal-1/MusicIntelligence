import { useState, useEffect, useRef } from 'react'
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

function JobProgress({ job, onRetry }) {
  if (!job) return null
  const failed = job.status === 'failed'
  const done = ['succeeded', 'failed', 'cancelled'].includes(job.status)
  const total = Number(job.progress_total || 0)
  const current = Number(job.progress_current || 0)
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
  const result = job.result || null

  return (
    <div className={`rounded-lg border p-3 space-y-2 ${failed ? 'bg-red-950/20 border-red-900/50' : 'bg-zinc-950 border-zinc-800'}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-white text-sm capitalize">{job.status}</p>
          <p className={failed ? 'text-red-300 text-xs mt-0.5 line-clamp-2' : 'text-zinc-500 text-xs mt-0.5 truncate'}>
            {failed ? (job.error || job.message || 'Job failed') : (job.message || 'Working')}
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
      {total > 0 && (
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${failed ? 'bg-red-400' : 'bg-brand'}`} style={{ width: `${pct}%` }} />
        </div>
      )}
      {done && result && (
        <div className="grid grid-cols-3 gap-2 pt-1">
          {['scanned', 'updated', 'new_songs'].map(key => result[key] !== undefined && (
            <div key={key} className="bg-zinc-900 rounded-md p-2">
              <p className="text-zinc-500 text-[11px]">{key.replace(/_/g, ' ')}</p>
              <p className="text-white text-sm font-semibold">{result[key]}</p>
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
  const [job, setJob]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)
  const fileRef = useRef(null)

  // Poll job until done
  useEffect(() => {
    if (!job?.id || ['succeeded', 'failed', 'cancelled'].includes(job.status)) return
    const t = setInterval(async () => {
      try {
        const updated = await api.get(`/jobs/${job.id}`)
        setJob(updated)
        if (['succeeded', 'failed', 'cancelled'].includes(updated.status)) clearInterval(t)
      } catch { clearInterval(t) }
    }, 1500)
    return () => clearInterval(t)
  }, [job?.id, job?.status])

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await api.postForm('/user/import-history/job', form)
      setJob(result)
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setLoading(false)
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
          {loading ? 'Uploading…' : 'Choose JSON file'}
          <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={handleFile} disabled={loading} />
        </label>
        {job?.status === 'succeeded' && (
          <span className="text-green-400 text-sm">
            ✓ Imported {job.result?.valid_tracks?.toLocaleString() ?? '?'} tracks
          </span>
        )}
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}
      <JobProgress job={job} onRetry={() => fileRef.current?.click()} />
    </div>
  )
}

export default function Features() {
  const [backfillResult, setBackfillResult] = useState(null)
  const [backfillLoading, setBackfillLoading] = useState(false)
  const [backfillPoll, setBackfillPoll] = useState(null)
  const [retryFailed, setRetryFailed] = useState(false)
  const [retryPartial, setRetryPartial] = useState(false)

  const [qualityResult, setQualityResult] = useState(null)
  const [qualityLoading, setQualityLoading] = useState(false)

  const [dedupPreview, setDedupPreview] = useState(null)
  const [dedupLoading, setDedupLoading] = useState(false)
  const [dedupApplying, setDedupApplying] = useState(false)
  const [dedupResult, setDedupResult] = useState(null)

  const [cacheClearing, setCacheClearing] = useState(false)
  const [cacheResult, setCacheResult] = useState(null)

  useEffect(() => {
    if (!backfillResult?.id || ['succeeded', 'failed', 'cancelled'].includes(backfillResult.status)) return

    const timer = setInterval(async () => {
      try {
        const job = await api.get(`/jobs/${backfillResult.id}`)
        setBackfillResult(job)
        if (['succeeded', 'failed', 'cancelled'].includes(job.status)) {
          clearInterval(timer)
          setBackfillPoll(null)
        }
      } catch (e) {
        setBackfillPoll({ error: e.message })
      }
    }, 1500)

    setBackfillPoll({ active: true })
    return () => clearInterval(timer)
  }, [backfillResult?.id, backfillResult?.status])

  async function handleBackfill() {
    setBackfillLoading(true)
    setBackfillPoll(null)
    try {
      const job = await api.post(`/user/backfill-metadata/job?limit=500&retry_partial=${retryPartial}&retry_failed=${retryFailed}`)
      setBackfillResult(job)
    } catch (e) {
      setBackfillResult({ error: e.message })
    } finally {
      setBackfillLoading(false)
    }
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

      <Section title="Metadata Enrichment" description="Fetch Last.fm tags and genre data for songs in your library.">
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input type="checkbox" checked={retryPartial} onChange={e => setRetryPartial(e.target.checked)} className="accent-brand" />
            Retry partial
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input type="checkbox" checked={retryFailed} onChange={e => setRetryFailed(e.target.checked)} className="accent-brand" />
            Retry failed
          </label>
          <ActionButton onClick={handleBackfill} loading={backfillLoading} icon={RefreshCw} label="Run Backfill" variant="primary" />
        </div>
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
