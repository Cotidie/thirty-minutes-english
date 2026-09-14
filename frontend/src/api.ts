import type { JobStatus } from './lib/progress'
import type { Ask, Example, LiveSession, PracticeTarget, Reading, Session, SessionSummary, Stars, TopicListing } from './types'

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
  topics: () => request<TopicListing>('/api/topics'),
  refreshTopics: () => request<TopicListing>('/api/topics/refresh', { method: 'POST' }),
  listSessions: () => request<SessionSummary[]>('/api/sessions'),
  getSession: (id: number) => request<Session>(`/api/sessions/${id}`),
  startGeneration: (topic: string | null) =>
    request<JobStatus>('/api/sessions', { method: 'POST', body: JSON.stringify({ topic }) }),
  getJob: (id: string) => request<JobStatus>(`/api/jobs/${id}`),
  /** Generations still running on the server, oldest first. */
  listJobs: () => request<JobStatus[]>('/api/jobs'),
  deleteSession: (id: number) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
  getStars: (id: number) => request<Stars>(`/api/sessions/${id}/stars`),
  setStars: (id: number, stars: Stars) =>
    request<Stars>(`/api/sessions/${id}/stars`, { method: 'PUT', body: JSON.stringify(stars) }),
  startReadAloud: (paragraph: string, sdp: string) =>
    request<LiveSession>('/api/read-aloud/sessions', { method: 'POST', body: JSON.stringify({ paragraph, sdp }) }),
  startPhrase: (topic: string | null, sdp: string) =>
    request<LiveSession>('/api/phrase/sessions', { method: 'POST', body: JSON.stringify({ topic, sdp }) }),
  startExample: (target: PracticeTarget, sdp: string) =>
    request<LiveSession>('/api/example/sessions', {
      method: 'POST',
      body: JSON.stringify({ sdp, expression: target.text, meaning: target.meaning, usage_note: target.note }),
    }),
  addExample: (example: { session_id: number; expression: string; user_text: string; coach_text: string; seconds: number }) =>
    request<Example>('/api/examples', { method: 'POST', body: JSON.stringify(example) }),
  listExamples: (sessionId: number) => request<Example[]>(`/api/examples?session_id=${sessionId}`),
  addAsk: (ask: { session_id: number | null; user_text: string; coach_text: string; seconds: number }) =>
    request<Ask>('/api/asks', { method: 'POST', body: JSON.stringify(ask) }),
  listAsks: (sessionId?: number) => request<Ask[]>(asksPath('/api/asks', sessionId)),
  /** Asks with their review cards, extracting any that do not have one yet. */
  askCards: (sessionId?: number) =>
    request<Ask[]>(asksPath('/api/asks/cards', sessionId), { method: 'POST' }),
  addReading: (reading: {
    session_id: number | null
    paragraph: string
    user_text: string
    coach_text: string
    seconds: number
  }) => request<Reading>('/api/readings', { method: 'POST', body: JSON.stringify(reading) }),
  /** Read-aloud rounds with the words the coach stopped on. */
  readingCorrections: (sessionId?: number) =>
    request<Reading[]>(asksPath('/api/readings/corrections', sessionId), { method: 'POST' }),
}

function asksPath(base: string, sessionId?: number): string {
  return sessionId === undefined ? base : `${base}?session_id=${sessionId}`
}
