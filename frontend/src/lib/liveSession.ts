// Pure state for one live round, driven by transport events. Transcript
// fragments are appended verbatim per speaker (the API asks for no trimming
// or spacing between deltas); Gemini's silence markers are dropped once the
// pieces have joined, since they arrive split across deltas.

type LiveStatus = 'connecting' | 'listening' | 'closing' | 'closed' | 'failed'

export interface LiveState {
  status: LiveStatus
  sessionId: string | null
  user: string
  coach: string
  seconds: number
  error: string | null
}

export interface LiveEvent {
  type: string
  session?: { id?: string }
  delta?: string
  usage?: { seconds?: number }
  error?: { message?: string }
  reason?: string
}

export const initialLiveState: LiveState = {
  status: 'connecting',
  sessionId: null,
  user: '',
  coach: '',
  seconds: 0,
  error: null,
}

const TRANSCRIPT_MARKERS = /<(?:no speech|noise|silence)>/gi

/** The transcript without Gemini's markers for silent or noisy turns. */
export function spoken(text: string): string {
  return text.replace(TRANSCRIPT_MARKERS, '')
}

export function applyLiveEvent(state: LiveState, event: LiveEvent): LiveState {
  switch (event.type) {
    case 'session.started':
      return { ...state, status: 'listening', sessionId: event.session?.id ?? state.sessionId }
    case 'session.input_transcript.delta':
      return { ...state, user: spoken(state.user + (event.delta ?? '')) }
    case 'session.output_transcript.delta':
      return { ...state, coach: spoken(state.coach + (event.delta ?? '')) }
    case 'session.usage.updated':
      return { ...state, seconds: event.usage?.seconds ?? state.seconds }
    case 'session.closed':
      return { ...state, status: 'closed', seconds: event.usage?.seconds ?? state.seconds }
    case 'error':
      return { ...state, error: event.error?.message ?? 'GPT-Live reported an error' }
    default:
      return state
  }
}

export function liveFailed(state: LiveState, message: string): LiveState {
  return { ...state, status: 'failed', error: message }
}
