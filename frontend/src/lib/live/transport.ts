// One live round, whichever provider is on: microphone in, coach audio out,
// transcript events to the caller. The backend picks the provider from
// settings; each transport turns its answer into the same LiveConnection.

import { api } from '../../api'
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
export const sayInstruction = (text: string) => `Now say exactly this, word for word, then stop: ${text}`

export async function connectLive(opts: LiveOptions): Promise<LiveConnection> {
  const provider = await api.voiceProvider()
  return provider === 'gemini' ? connectGemini(opts) : connectOpenAI(opts)
}
