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
  /** Hands the coach one assessor finding to interrupt with. */
  correct(finding: Finding): void
  /** Tells the coach the reader's repeat came out right. */
  confirm(): void
  /** Hands the coach every open finding at once, after the reader is done. */
  review(findings: Finding[]): void
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
export const CONFIRM_INSTRUCTION = 'Repeat OK: the reader repeated it right. Say "Good." and nothing else.'
export const sayInstruction = (text: string) => `Now say exactly this, word for word, then stop: ${text}`

export const correctionInstruction = (f: Finding) =>
  f.kind === 'pronunciation'
    ? `Correction: the reader mispronounced "${f.word}" (heard ${f.heard}). Interrupt now: say what you heard, then the word the right way, one short fix, then "Go on."`
    : `Correction: the reader paused inside "${f.word}" (${f.heard}). Interrupt now: say "${f.word}" as one piece, then "From '${f.word.split(' ')[0]}'."`

/** One review of everything open; with nothing open the coach just signs off. */
export const reviewInstruction = (findings: Finding[]) => {
  if (findings.length === 0) return FINISH_INSTRUCTION
  const items = findings
    .map((f, i) => (f.kind === 'pronunciation' ? `${i + 1}) "${f.word}": heard ${f.heard}.` : `${i + 1}) "${f.word}": paused after "${f.word.split(' ')[0]}".`))
    .join(' ')
  return `Review: the reader has finished. Go through these in order, each under five seconds: what was heard, the right way, one short fix. ${items} Then say: "Read those back to me." and wait.`
}

export async function connectLive(opts: LiveOptions): Promise<LiveConnection> {
  const provider = await api.voiceProvider()
  return provider === 'gemini' ? connectGemini(opts) : connectOpenAI(opts)
}
