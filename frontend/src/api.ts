import type { JobStatus } from './lib/progress'
import type {
  AssessorSession,
  Correction,
  CorpusEntry,
  Example,
  ExampleFeedback,
  Expression,
  KeyTestResult,
  LiveSession,
  Note,
  PictureFace,
  Summary,
  SummaryFeedback,
  PracticeTarget,
  Reading,
  Session,
  SessionSummary,
  SettingsUpdate,
  SettingsView,
  Stars,
  TopicLibrary,
  TopicListing,
  VocabularyItem,
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
  /** Every topic with the days it led the news and the sessions written on it. */
  topicLibrary: () => request<TopicLibrary>('/api/topics/all'),
  listSessions: () => request<SessionSummary[]>('/api/sessions'),
  /** The whole expression corpus; the corpus page searches it in the browser. */
  corpus: () => request<CorpusEntry[]>('/api/expressions'),
  /** Out of the corpus and out of every session that taught it. */
  deleteExpression: (id: number) => request<void>(`/api/expressions/${id}`, { method: 'DELETE' }),
  /** Fails with a 409 when a session was written on it. */
  deleteTopic: (id: number) => request<void>(`/api/topics/${id}`, { method: 'DELETE' }),
  getSession: (id: number) => request<Session>(`/api/sessions/${id}`),
  startGeneration: (topic: string | null) =>
    request<JobStatus>('/api/sessions', { method: 'POST', body: JSON.stringify({ topic }) }),
  getJob: (id: string) => request<JobStatus>(`/api/jobs/${id}`),
  /** Generations still running on the server, oldest first. */
  listJobs: () => request<JobStatus[]>('/api/jobs'),
  /** Stops a running generation; nothing from it is saved. */
  cancelJob: (id: string) => request<JobStatus>(`/api/jobs/${id}`, { method: 'DELETE' }),
  deleteSession: (id: number) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
  /** Another corpus expression in this one's place; the one swapped out counts as used. */
  swapExpression: (sessionId: number, expressionId: number) =>
    request<Expression>(`/api/sessions/${sessionId}/expressions/${expressionId}/swap`, { method: 'POST' }),
  /** One more corpus expression, taught after the others and picked as a swap picks one. */
  addExpression: (sessionId: number) => request<Expression>(`/api/sessions/${sessionId}/expressions`, { method: 'POST' }),
  /** One of a word's pictures drawn again in the configured style and saved: the example sentence as it is,
   * or a fresh scene for Practice. The item as it now is. */
  redrawPicture: (sessionId: number, index: number, face: PictureFace) =>
    request<VocabularyItem>(`/api/sessions/${sessionId}/pictures/${index}`, { method: 'POST', body: JSON.stringify({ face }) }),
  /** The sentence read aloud by the voice provider, as audio. */
  speak: async (text: string): Promise<Blob> => {
    const res = await fetch('/api/speech', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body && typeof body.detail === 'string' ? body.detail : `${res.status} ${res.statusText}`)
    }
    return res.blob()
  },
  getStars: (id: number) => request<Stars>(`/api/sessions/${id}/stars`),
  /** One item's star; the session's stars as they then are, others' included. */
  setStar: (id: number, kind: keyof Stars, item: number, starred: boolean) =>
    request<Stars>(`/api/sessions/${id}/stars/${kind}/${item}`, { method: 'PUT', body: JSON.stringify({ starred }) }),
  getNote: (id: number) => request<Note>(`/api/sessions/${id}/note`),
  /** `keepalive` lets the save finish after the page closes. */
  setNote: (id: number, text: string, keepalive = false) =>
    request<Note>(`/api/sessions/${id}/note`, { method: 'PUT', body: JSON.stringify({ text }), keepalive }),
  getSettings: () => request<SettingsView>('/api/settings'),
  /** Fetches every provider's model list now; the settings as they then read. */
  refreshModels: () => request<SettingsView>('/api/settings/models/refresh', { method: 'POST' }),
  /** Keeps a model on its list's menu, or lets it go; saved at once. The settings as they then read. */
  pinModel: (catalog: string, model: string, pinned: boolean) =>
    request<SettingsView>('/api/settings/models/pin', { method: 'POST', body: JSON.stringify({ catalog, model, pinned }) }),
  putSettings: (values: SettingsUpdate) =>
    request<SettingsView>('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  /** One authenticated call to the provider with the typed key, or the saved one when blank. */
  testKey: (key: string, value: string) =>
    request<KeyTestResult>('/api/settings/test-key', { method: 'POST', body: JSON.stringify({ key, value }) }),
  startReadAloud: (paragraph: string) =>
    request<LiveSession>('/api/read-aloud/sessions', { method: 'POST', body: JSON.stringify({ paragraph }) }),
  /** Azure token for the assessor; 503 until AZURE_SPEECH_KEY is set. */
  assessorToken: () => request<AssessorSession>('/api/assessor/token'),
  startExample: (target: PracticeTarget) =>
    request<LiveSession>('/api/example/sessions', {
      method: 'POST',
      body: JSON.stringify({ word: target.word, meaning: target.meaning, pos: target.pos }),
    }),
  /** The written half of a practice round: the sentence the native way, plus a short line per change. */
  exampleFeedback: (target: PracticeTarget, userText: string) =>
    request<ExampleFeedback>('/api/example/feedback', {
      method: 'POST',
      body: JSON.stringify({ word: target.word, pos: target.pos, meaning: target.meaning, user_text: userText, scene: target.scene ?? '' }),
    }),
  /** A sentence made with one of the session's words. */
  addExample: (example: {
    session_id: number
    vocabulary_id: number
    user_text: string
    coach_text: string
    seconds: number
  }) =>
    request<Example>('/api/examples', { method: 'POST', body: JSON.stringify(example) }),
  listExamples: (sessionId: number) => request<Example[]>(`/api/examples?session_id=${sessionId}`),
  /** Gemini's transcription model, primed with the paragraph's words. */
  startSummary: (paragraph: string) =>
    request<LiveSession>('/api/summary/sessions', { method: 'POST', body: JSON.stringify({ paragraph }) }),
  /** A spoken summary judged against its paragraph: what was missed, the wording fixed, and the summary with the fixes in. */
  summaryFeedback: (paragraph: string, userText: string) =>
    request<SummaryFeedback>('/api/summary/feedback', { method: 'POST', body: JSON.stringify({ paragraph, user_text: userText }) }),
  addSummary: (summary: { paragraph_id: number; user_text: string; feedback: SummaryFeedback; seconds: number }) =>
    request<Summary>('/api/summaries', { method: 'POST', body: JSON.stringify(summary) }),
  listSummaries: (sessionId: number) => request<Summary[]>(`/api/summaries?session_id=${sessionId}`),
  addReading: (reading: {
    paragraph_id: number
    user_text: string
    seconds: number
    corrections: Correction[]
  }) => request<Reading>('/api/readings', { method: 'POST', body: JSON.stringify(reading) }),
  /** A session's read-aloud rounds with the findings the assessor made, newest first. */
  listReadings: (sessionId: number) => request<Reading[]>(`/api/readings?session_id=${sessionId}`),
}
