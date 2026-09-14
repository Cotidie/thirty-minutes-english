import { useEffect, useState } from 'react'
import { api } from '../api'
import type { JobStatus } from './progress'

export const JOB_POLL_MS = 1000

/**
 * The session being written, if any. The server owns the job, so on mount we
 * ask it for one still running: leaving the page and coming back, or a reload,
 * shows the same progress bar.
 */
export function useGenerationJob(onDone: (sessionId: number) => void) {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const running = job !== null && job.status === 'running'

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
    const timer = setInterval(() => {
      api
        .getJob(job.id)
        .then((next) => {
          setJob(next)
          if (next.status === 'done' && next.session_id !== null) onDone(next.session_id)
          if (next.status === 'failed') setError(next.error ?? 'generation failed')
        })
        .catch((e: Error) => {
          setError(e.message)
          setJob(null)
        })
    }, JOB_POLL_MS)
    return () => clearInterval(timer)
  }, [running, job, onDone])

  async function start(topic: string | null) {
    setError(null)
    try {
      setJob(await api.startGeneration(topic))
    } catch (e) {
      setError((e as Error).message)
      setJob(null)
    }
  }

  return { job, running, error, start }
}
