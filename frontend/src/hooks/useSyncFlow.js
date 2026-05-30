import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

function isDone(job) {
  return ['succeeded', 'failed', 'cancelled'].includes(job?.status)
}

export function useSyncFlow({ onSyncFinished, onEnrichmentFinished } = {}) {
  const [syncing, setSyncing] = useState(false)
  const [syncJob, setSyncJob] = useState(null)
  const [enrichmentJob, setEnrichmentJob] = useState(null)
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
    const setter = kind === 'enrichment' ? setEnrichmentJob : setSyncJob
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
        } else {
          onEnrichmentFinished?.(job)
        }

        setTimeout(() => setter(null), 4000)
      } catch (e) {
        console.error(e)
        failuresRef.current[kind] = (failuresRef.current[kind] || 0) + 1
        if (failuresRef.current[kind] < 3) return
        setter(prev => prev ? { ...prev, status: 'failed', error: e.message, message: 'Lost connection while checking job status' } : prev)
        clearTimer(kind)
      }
    }, 1500)
  }, [clearTimer, onEnrichmentFinished, onSyncFinished, refreshSyncStatus])

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
    return () => {
      clearTimer('sync')
      clearTimer('enrichment')
    }
  }, [clearTimer, refreshSyncStatus])

  return {
    syncing,
    syncJob,
    enrichmentJob,
    syncStatus,
    syncError,
    syncAtLimit,
    startSync,
    startEnrichment,
    refreshSyncStatus,
  }
}
