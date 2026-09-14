import type { JobStatus } from './lib/progress'
import type { Ask, LiveSession, Session, SessionSummary } from './types'

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
  startReadAloud: (paragraph: string, sdp: string) =>
    request<LiveSession>('/api/read-aloud/sessions', { method: 'POST', body: JSON.stringify({ paragraph, sdp }) }),
  startPhrase: (topic: string | null, sdp: string) =>
    request<LiveSession>('/api/phrase/sessions', { method: 'POST', body: JSON.stringify({ topic, sdp }) }),
  addAsk: (ask: { session_id: number | null; user_text: string; coach_text: string; seconds: number }) =>
    request<Ask>('/api/asks', { method: 'POST', body: JSON.stringify(ask) }),
  listAsks: (sessionId?: number) => request<Ask[]>(asksPath('/api/asks', sessionId)),
  /** Asks with their review cards, extracting any that do not have one yet. */
  askCards: (sessionId?: number) =>
    request<Ask[]>(asksPath('/api/asks/cards', sessionId), { method: 'POST' }),
}

function asksPath(base: string, sessionId?: number): string {
  return sessionId === undefined ? base : `${base}?session_id=${sessionId}`
}
