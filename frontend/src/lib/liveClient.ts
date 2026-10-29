// The coaches, each a live round on Gemini Live with its own way of starting.
// Summarize goes to Gemini's transcription model.

import { api } from '../api'
import type { PracticeTarget } from '../types'
import { connectGemini, connectGeminiTranscription } from './live/geminiWebsocket'
import type { LiveConnection, LiveOptions } from './live/transport'

export type { LiveConnection, LiveOptions } from './live/transport'

type RoundOptions = Omit<LiveOptions, 'start'>

/** The coach that says one pronunciation correction on a paragraph the user read aloud. */
export function connectReadAloud(paragraph: string, opts: RoundOptions): Promise<LiveConnection> {
  return connectGemini({ ...opts, start: () => api.startReadAloud(paragraph) })
}

/** Writes down what the user says a paragraph is about, in English or Korean, primed with the paragraph's words. It never answers. */
export function connectSummary(paragraph: string, opts: RoundOptions): Promise<LiveConnection> {
  return connectGeminiTranscription({ ...opts, start: () => api.startSummary(paragraph) })
}

/** One sentence made with a word, said back the native way with a line of feedback. */
export function connectExample(target: PracticeTarget, opts: RoundOptions): Promise<LiveConnection> {
  return connectGemini({ ...opts, start: () => api.startExample(target) })
}
