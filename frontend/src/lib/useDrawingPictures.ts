import { useEffect, useState } from 'react'
import { api } from '../api'

const POLL_MS = 3000

/**
 * Whether the job that wrote this session is still drawing its pictures, for the places held for them.
 * A job is its starter's own passing state, so this asks over and over; the pictures themselves come
 * through the session's own reads, as each lands.
 */
export function useDrawingPictures(sessionId: number): boolean {
  const [drawing, setDrawing] = useState(false)

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const check = async () => {
      const jobs = await api.listJobs().catch(() => [])
      if (!live) return
      const running = jobs.some((job) => job.session_id === sessionId && job.status === 'running')
      setDrawing(running)
      if (running) timer = setTimeout(() => void check(), POLL_MS)
    }
    void check()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [sessionId])

  return drawing
}
