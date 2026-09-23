import type { JobStatus } from './lib/progress'
import type {
  Ask,
  AssessorSession,
  Correction,
  Example,
  ExampleFeedback,
  KeyTestResult,
  LiveSession,
  PictureStyles,
  PracticeTarget,
  Reading,
  Session,
  SessionSummary,
  SettingsUpdate,
  SettingsView,
  Stars,
  TopicListing,
  VocabularyItem,
  VoiceProvider,
} from './types'

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
  /** Stops a running generation; nothing from it is saved. */
  cancelJob: (id: string) => request<JobStatus>(`/api/jobs/${id}`, { method: 'DELETE' }),
  deleteSession: (id: number) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
  /** A fresh scene for one word, drawn in `style` (blank: the configured one) and saved; the item as it now is. */
  redrawPicture: (sessionId: number, index: number, style = '') =>
    request<VocabularyItem>(`/api/sessions/${sessionId}/pictures/${index}`, { method: 'POST', body: JSON.stringify({ style }) }),
  /** The picture styles on offer and the configured one, from the IMAGE_STYLE setting. */
  pictureStyles: async (): Promise<PictureStyles> => {
    const { fields } = await request<SettingsView>('/api/settings')
    const f = fields.find((x) => x.key === 'IMAGE_STYLE')
    return { current: f?.value || f?.default || '', options: f?.options ?? [] }
  },
  getStars: (id: number) => request<Stars>(`/api/sessions/${id}/stars`),
  setStars: (id: number, stars: Stars) =>
    request<Stars>(`/api/sessions/${id}/stars`, { method: 'PUT', body: JSON.stringify(stars) }),
  getSettings: () => request<SettingsView>('/api/settings'),
  /** Fetches every provider's model list now; the settings as they then read. */
  refreshModels: () => request<SettingsView>('/api/settings/models/refresh', { method: 'POST' }),
  putSettings: (values: SettingsUpdate) =>
    request<SettingsView>('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  /** One authenticated call to the provider with the typed key, or the saved one when blank. */
  testKey: (key: string, value: string) =>
    request<KeyTestResult>('/api/settings/test-key', { method: 'POST', body: JSON.stringify({ key, value }) }),
  /** Which voice provider a round will land on, read right before opening one. */
  voiceProvider: async (): Promise<VoiceProvider> => {
    const { fields } = await request<SettingsView>('/api/settings')
    return fields.find((f) => f.key === 'VOICE_PROVIDER')?.value === 'gemini' ? 'gemini' : 'openai'
  },
  /** `sdp` is the WebRTC offer; only the OpenAI provider takes one. */
  startReadAloud: (paragraph: string, sdp?: string) =>
    request<LiveSession>('/api/read-aloud/sessions', { method: 'POST', body: JSON.stringify({ paragraph, sdp }) }),
  /** Azure token for the assessor; 503 until AZURE_SPEECH_KEY is set. */
  assessorToken: () => request<AssessorSession>('/api/assessor/token'),
  phrasing: (paragraph: string) =>
    request<{ breaks: number[] }>('/api/phrasing', { method: 'POST', body: JSON.stringify({ paragraph }) }),
  startPhrase: (topic: string | null, sdp?: string) =>
    request<LiveSession>('/api/phrase/sessions', { method: 'POST', body: JSON.stringify({ topic, sdp }) }),
  startExample: (target: PracticeTarget, sdp?: string) =>
    request<LiveSession>('/api/example/sessions', {
      method: 'POST',
      body: JSON.stringify({ sdp, expression: target.text, meaning: target.meaning, usage_note: target.note }),
    }),
  /** The written half of a practice round: the sentence the native way, plus a short line per change. */
  exampleFeedback: (target: PracticeTarget, userText: string) =>
    request<ExampleFeedback>('/api/example/feedback', {
      method: 'POST',
      body: JSON.stringify({
        expression: target.text,
        meaning: target.meaning,
        usage_note: target.note,
        user_text: userText,
        kind: target.kind,
        scene: target.scene ?? '',
      }),
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
    corrections: Correction[]
  }) => request<Reading>('/api/readings', { method: 'POST', body: JSON.stringify(reading) }),
  /** Read-aloud rounds with the findings the assessor made, newest first. */
  listReadings: (sessionId?: number) => request<Reading[]>(asksPath('/api/readings', sessionId)),
}

function asksPath(base: string, sessionId?: number): string {
  return sessionId === undefined ? base : `${base}?session_id=${sessionId}`
}
