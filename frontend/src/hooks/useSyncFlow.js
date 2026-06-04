import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

function isDone(job) {
  return ['succeeded', 'failed', 'cancelled'].includes(job?.status)
}

function isTransientServerError(error) {
  return error?.status >= 500 || /bad gateway|failed to fetch|network/i.test(error?.message || '')
}

function setterForKind(kind, setters) {
  if (kind === 'enrichment') return setters.setEnrichmentJob
  if (kind === 'import') return setters.setImportJob
  return setters.setSyncJob
}

export function useSyncFlow({ onSyncFinished, onEnrichmentFinished } = {}) {
  const [syncing, setSyncing] = useState(false)
  const [syncJob, setSyncJob] = useState(null)
  const [enrichmentJob, setEnrichmentJob] = useState(null)
  const [importJob, setImportJob] = useState(null)
  const [syncStatus, setSyncStatus] = useState(null)
  const [syncError, setSyncError] = useState(null)
  const [syncAtLimit, setSyncAtLimit] = useState(false)
  const timersRef = useRef({})
  const failuresRef = useRef({})

  const refreshSyncStatus = useCallback(async () => {
    try {
      const status = await api.get('/user/sync-status')
      setSyncStatus(status)
      return status
    } catch (e) {
      console.error(e)
      return null
    }
  }, [])

  const clearTimer = useCallback((kind) => {
    if (timersRef.current[kind]) {
      clearInterval(timersRef.current[kind])
      timersRef.current[kind] = null
    }
  }, [])

  const startPolling = useCallback((kind, jobId) => {
    const setter = setterForKind(kind, { setSyncJob, setEnrichmentJob, setImportJob })
    clearTimer(kind)
    failuresRef.current[kind] = 0
    timersRef.current[kind] = setInterval(async () => {
      try {
        const job = await api.get(`/jobs/${jobId}`)
        failuresRef.current[kind] = 0
        setter(job)
        if (!isDone(job)) return

        clearTimer(kind)
        await refreshSyncStatus()

        if (kind === 'sync') {
          onSyncFinished?.(job)
          const result = job.result || {}
          // Spotify caps recent-plays at 50 tracks per call — warn the user.
          if (job.status === 'succeeded' && (result.new_history_rows ?? 0) >= 50) {
            setSyncAtLimit(true)
          }
          if (result.enrichment_queued && result.enrichment_job_id) {
            const queued = {
              id: result.enrichment_job_id,
              job_type: 'backfill_metadata',
              status: 'queued',
              progress_current: 0,
              progress_total: 1,
              message: 'Queued tag and genre enrichment',
            }
            setEnrichmentJob(queued)
            startPolling('enrichment', result.enrichment_job_id)
          }
        } else if (kind === 'import') {
          if (job.status === 'succeeded') {
            localStorage.removeItem('musicintel:import-job-id')
          }
        } else {
          onEnrichmentFinished?.(job)
        }

        setTimeout(() => setter(null), 4000)
      } catch (e) {
        console.error(e)
        failuresRef.current[kind] = (failuresRef.current[kind] || 0) + 1
        const transient = isTransientServerError(e)
        const maxFailures = transient ? 40 : 3
        setter(prev => prev ? {
          ...prev,
          error: transient ? null : e.message,
          message: transient
            ? 'Backend is restarting. Still checking job status...'
            : 'Lost connection while checking job status',
        } : prev)
        if (failuresRef.current[kind] < maxFailures) return
        setter(prev => prev ? { ...prev, status: 'failed', error: e.message, message: 'Lost connection while checking job status' } : prev)
        clearTimer(kind)
      }
    }, 1500)
  }, [clearTimer, onEnrichmentFinished, onSyncFinished, refreshSyncStatus])

  const resumeJob = useCallback((job) => {
    if (!job?.id) return
    if (job.job_type === 'sync_history') {
      setSyncJob(job)
      if (!isDone(job)) startPolling('sync', job.id)
      return
    }
    if (job.job_type === 'backfill_metadata') {
      setEnrichmentJob(job)
      if (!isDone(job)) startPolling('enrichment', job.id)
      return
    }
    if (job.job_type === 'import_history') {
      setImportJob(job)
      localStorage.setItem('musicintel:import-job-id', job.id)
      if (!isDone(job)) startPolling('import', job.id)
    }
  }, [startPolling])

  async function startSync() {
    setSyncing(true)
    setSyncError(null)
    try {
      const job = await api.post('/user/sync-history/job')
      setSyncJob(job)
      startPolling('sync', job.id)
      return job
    } catch (e) {
      const msg = e?.message || 'Sync failed. Please try again.'
      setSyncError(msg)
      throw e
    } finally {
      setSyncing(false)
    }
  }

  async function startEnrichment({ retryPartial = true, retryFailed = true, limit = 500 } = {}) {
    const job = await api.post(`/user/backfill-metadata/job?limit=${limit}&retry_partial=${retryPartial}&retry_failed=${retryFailed}`)
    setEnrichmentJob(job)
    startPolling('enrichment', job.id)
    return job
  }

  useEffect(() => {
    refreshSyncStatus()
    api.get('/jobs', { limit: 10 })
      .then(data => {
        const active = (data.items || []).filter(job => !isDone(job))
        active.forEach(resumeJob)
      })
      .catch(() => {})

    const storedImportJobId = localStorage.getItem('musicintel:import-job-id')
    if (storedImportJobId) {
      api.get(`/jobs/${storedImportJobId}`)
        .then(resumeJob)
        .catch(() => localStorage.removeItem('musicintel:import-job-id'))
    }

    const onJobStarted = (event) => resumeJob(event.detail?.job)
    window.addEventListener('musicintel:job-started', onJobStarted)
    return () => {
      clearTimer('sync')
      clearTimer('enrichment')
      clearTimer('import')
      window.removeEventListener('musicintel:job-started', onJobStarted)
    }
  }, [clearTimer, refreshSyncStatus, resumeJob])

  return {
    syncing,
    syncJob,
    enrichmentJob,
    importJob,
    syncStatus,
    syncError,
    syncAtLimit,
    startSync,
    startEnrichment,
    refreshSyncStatus,
  }
}
