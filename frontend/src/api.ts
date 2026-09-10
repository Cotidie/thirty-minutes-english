import type { JobStatus } from './lib/progress'
import type { Session, SessionSummary } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body && typeof body.detail === 'string' ? body.detail : `${res.status} ${res.statusText}`
    throw new Error(detail)
  }
  return body as T
}

export const api = {
  topics: () => request<string[]>('/api/topics'),
  listSessions: () => request<SessionSummary[]>('/api/sessions'),
  getSession: (id: number) => request<Session>(`/api/sessions/${id}`),
  startGeneration: (topic: string | null) =>
    request<JobStatus>('/api/sessions', { method: 'POST', body: JSON.stringify({ topic }) }),
  getJob: (id: string) => request<JobStatus>(`/api/jobs/${id}`),
  deleteSession: (id: number) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
}
