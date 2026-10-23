// The coaches, each a live round with its own way of starting. The
// provider (OpenAI over WebRTC, Gemini over WebSocket) is whatever Settings
// says at the moment the round opens; see lib/live/transport.ts. Summarize
// always goes to Gemini's transcription model.

import { api } from '../api'
import type { PracticeTarget } from '../types'
import { connectGeminiTranscription } from './live/geminiWebsocket'
import { connectLive, type LiveConnection, type LiveOptions } from './live/transport'

export type { LiveConnection, LiveOptions } from './live/transport'

type RoundOptions = Omit<LiveOptions, 'start'>

/** The coach that says one pronunciation correction on a paragraph the user read aloud. */
export function connectReadAloud(paragraph: string, opts: RoundOptions): Promise<LiveConnection> {
  return connectLive({ ...opts, start: (sdp) => api.startReadAloud(paragraph, sdp) })
}

/** Writes down what the user says a paragraph is about, in English or Korean, primed with the paragraph's words. It never answers. */
export function connectSummary(paragraph: string, opts: RoundOptions): Promise<LiveConnection> {
  return connectGeminiTranscription({ ...opts, start: () => api.startSummary(paragraph) })
}

/** One sentence made with an expression or word, said back the native way with a line of feedback. */
export function connectExample(target: PracticeTarget, opts: RoundOptions): Promise<LiveConnection> {
  return connectLive({ ...opts, start: (sdp) => api.startExample(target, sdp) })
}
