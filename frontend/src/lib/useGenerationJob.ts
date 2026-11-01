import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { JobStatus } from './progress'

const JOB_POLL_MS = 1000

/**
 * The session being written, or the last one that failed, if any. The server owns
 * the job, so on mount we ask it for one still open: leaving the page and coming
 * back, or a reload, shows the same progress bar. A failed job stays, error and
 * all, until `close`. `error` is for requests that did not get through.
 * `onSession` fires once, when the job saves its session: the text is written
 * then, and the pictures go on landing on it while the job runs.
 */
export function useGenerationJob(onSession: (sessionId: number) => void) {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const running = job !== null && job.status === 'running'

  /** Reads the job again: it leaves the page once it is over, and its session opens the moment it is saved. */
  const readAgain = useCallback(
    (current: JobStatus) =>
      api
        .getJob(current.id)
        .then((next) => {
          setJob(next.status === 'cancelled' || next.status === 'done' ? null : next)
          if (next.session_id !== null && current.session_id === null) onSession(next.session_id)
        })
        .catch((e: Error) => {
          setError(e.message)
          setJob(null)
        }),
    [onSession],
  )

  useEffect(() => {
    let live = true
    api
      .listJobs()
      .then((jobs) => {
        if (live && jobs.length > 0) setJob(jobs[jobs.length - 1])
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [])

  useEffect(() => {
    if (!running || !job) return
    const timer = setInterval(() => void readAgain(job), JOB_POLL_MS)
    return () => clearInterval(timer)
  }, [running, job, readAgain])

  async function start(topic: string | null) {
    setError(null)
    try {
      const started = await api.startGeneration(topic)
      setJob(started)
      // At once: stopping costs from the moment the worker takes it, and Cancel must say so.
      await readAgain(started)
    } catch (e) {
      setError((e as Error).message)
      setJob(null)
    }
  }

  /** Cancels the running job, or dismisses the failed one. */
  async function close() {
    if (!job) return
    setJob(null)
    try {
      await api.cancelJob(job.id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return { job, running, error, start, close }
}
