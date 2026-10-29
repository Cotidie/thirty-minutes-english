// What a live round hands its caller: microphone in, coach audio out,
// transcript events out. lib/live/geminiWebsocket.ts carries the rounds.

import type { Finding } from '../assessor/judge'
import type { LiveEvent } from '../liveSession'
import type { LiveSession } from '../../types'

export interface LiveConnection {
  /** The live microphone track, so the UI can show that sound is going in. */
  microphone: MediaStream
  /** Has the coach read this text aloud, word for word. */
  say(text: string): void
  /** Hands the coach the finding the reader clicked; the reader is listening. */
  correct(finding: Finding): void
  /** Ends the round. `session.closed` arrives through onEvent afterwards. */
  close(): void
  /** Drops everything without waiting for the final event. */
  dispose(): void
}

export interface LiveOptions {
  /** Opens the upstream round. */
  start: () => Promise<LiveSession>
  audio: HTMLAudioElement
  onEvent: (event: LiveEvent) => void
  onDisconnect: () => void
}

export const sayInstruction = (text: string) => `Now say exactly this, word for word, then stop: ${text}`

/** The finding the reader clicked; the prompt says how to say it. */
export const correctionInstruction = (f: Finding) => `Correction: "${f.word}", heard ${f.heard}.`
