// One live round, whichever provider is on: microphone in, coach audio out,
// transcript events to the caller. The backend picks the provider from
// settings; each transport turns its answer into the same LiveConnection.

import { api } from '../../api'
import type { Finding } from '../assessor/judge'
import type { LiveEvent } from '../liveSession'
import type { LiveSession } from '../../types'
import { connectGemini } from './geminiWebsocket'
import { connectOpenAI } from './openaiWebrtc'

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
  /** Opens the upstream round. Gets our SDP offer on the OpenAI path only. */
  start: (sdp?: string) => Promise<LiveSession>
  audio: HTMLAudioElement
  onEvent: (event: LiveEvent) => void
  onDisconnect: () => void
}

export const sayInstruction = (text: string) => `Now say exactly this, word for word, then stop: ${text}`

/** The finding the reader clicked; the prompt says how to say it. */
export const correctionInstruction = (f: Finding) =>
  f.kind === 'pronunciation'
    ? `Correction: "${f.word}", heard ${f.heard}.`
    : `Correction: "${f.word}", paused after "${f.word.split(' ')[0]}".`

export async function connectLive(opts: LiveOptions): Promise<LiveConnection> {
  const provider = await api.voiceProvider()
  return provider === 'gemini' ? connectGemini(opts) : connectOpenAI(opts)
}
