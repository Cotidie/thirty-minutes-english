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
  /** Tells the coach the round is over, so it signs off. */
  finish(): void
  /** Has the coach read this text aloud, word for word. */
  say(text: string): void
  /** Hands the coach the finding the reader clicked; the reader is listening. */
  correct(finding: Finding): void
  /** Tells the coach the reader read it right this time. */
  confirm(): void
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

export const FINISH_INSTRUCTION = 'The round is over. Say your closing now.'
export const CONFIRM_INSTRUCTION = 'Repeat OK: the reader read it right this time. Say "Good." and nothing else.'
export const sayInstruction = (text: string) => `Now say exactly this, word for word, then stop: ${text}`

/** Two beats: the problem as the reader said it, then the right version. The reader asked by clicking. */
export const correctionInstruction = (f: Finding) =>
  f.kind === 'pronunciation'
    ? `Correction: the reader mispronounced "${f.word}" (heard ${f.heard}) and is asking about it now. Two beats: "You said" the word as they said it, then "It's" the word right. Then "Try it."`
    : `Correction: the reader paused inside "${f.word}" (${f.heard}) and is asking about it now. Two beats: "You stopped after '${f.word.split(' ')[0]}'", then "${f.word}" as one piece. Then "Try it."`

export async function connectLive(opts: LiveOptions): Promise<LiveConnection> {
  const provider = await api.voiceProvider()
  return provider === 'gemini' ? connectGemini(opts) : connectOpenAI(opts)
}
