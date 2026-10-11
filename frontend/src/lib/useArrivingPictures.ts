import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Session } from '../types'

const POLL_MS = 3000

/**
 * A session opens as soon as its text is written, while the job that wrote it still
 * draws the pictures. True for that time; the session is read again every few seconds,
 * and once more when the job ends, so each picture shows up as it lands.
 */
export function useArrivingPictures(sessionId: number, onSession: (session: Session) => void): boolean {
  const [arriving, setArriving] = useState(false)

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let was = false
    const check = async () => {
      const jobs = await api.listJobs().catch(() => [])
      if (!live) return
      const drawing = jobs.some((job) => job.session_id === sessionId && job.status === 'running')
      setArriving(drawing)
      if (drawing || was) await api.getSession(sessionId).then((s) => live && onSession(s)).catch(() => undefined)
      was = drawing
      if (drawing && live) timer = setTimeout(check, POLL_MS)
    }
    void check()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [sessionId, onSession])

  return arriving
}
