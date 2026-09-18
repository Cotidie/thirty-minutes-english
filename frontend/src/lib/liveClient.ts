// The three coaches, each a live round with its own way of starting. The
// provider (OpenAI over WebRTC, Gemini over WebSocket) is whatever Settings
// says at the moment the round opens; see lib/live/transport.ts.

import { api } from '../api'
import type { PracticeTarget } from '../types'
import { connectLive, type LiveConnection, type LiveOptions } from './live/transport'

export type { LiveConnection, LiveOptions } from './live/transport'

type RoundOptions = Omit<LiveOptions, 'start'>

/** Pronunciation and phrasing coaching on one paragraph the user reads aloud. */
export function connectReadAloud(paragraph: string, opts: RoundOptions): Promise<LiveConnection> {
  return connectLive({ ...opts, start: (sdp) => api.startReadAloud(paragraph, sdp) })
}

/** One "how do I say this in English" question, with the session topic for context. */
export function connectAsk(topic: string | null, opts: RoundOptions): Promise<LiveConnection> {
  return connectLive({ ...opts, start: (sdp) => api.startPhrase(topic, sdp) })
}

/** One sentence made with an expression or word, said back the native way with a line of feedback. */
export function connectExample(target: PracticeTarget, opts: RoundOptions): Promise<LiveConnection> {
  return connectLive({ ...opts, start: (sdp) => api.startExample(target, sdp) })
}
