// Pure translation of one Gemini Live server message into the events the
// rest of the app already understands (the OpenAI names), plus the audio
// chunks and turn signals the transport itself acts on. A coach and the
// transcription model speak the same protocol but mean different things by it.

import { spoken, type LiveEvent } from '../liveSession'

interface Part {
  inlineData?: { mimeType?: string; data?: string }
  text?: string
}

export interface GeminiServerMessage {
  setupComplete?: object
  serverContent?: {
    modelTurn?: { parts?: Part[] }
    inputTranscription?: { text?: string }
    outputTranscription?: { text?: string }
    interrupted?: boolean
    generationComplete?: boolean
  }
  /** Sent by the transcription model as each utterance starts and ends. */
  voiceActivity?: { type?: 'ACTIVITY_START' | 'ACTIVITY_END' }
  goAway?: { timeLeft?: string }
  error?: { message?: string; status?: string }
}

export interface Decoded {
  events: LiveEvent[]
  /** Base64 16-bit PCM at 24 kHz, in order. */
  audio: string[]
  /** The user spoke over the coach: drop whatever is still queued to play. */
  interrupted: boolean
  /** The server will close the socket soon; the close that follows is not a drop. */
  goAway: boolean
}

export function decodeServerMessage(msg: GeminiServerMessage): Decoded {
  const events: LiveEvent[] = []
  const audio: string[] = []
  const content = msg.serverContent
  if (msg.setupComplete) events.push({ type: 'session.started' })
  const heard = spoken(content?.inputTranscription?.text ?? '')
  if (heard) events.push({ type: 'session.input_transcript.delta', delta: heard })
  const said = spoken(content?.outputTranscription?.text ?? '')
  if (said) events.push({ type: 'session.output_transcript.delta', delta: said })
  for (const part of content?.modelTurn?.parts ?? []) {
    if (part.inlineData?.data && (part.inlineData.mimeType ?? '').startsWith('audio/pcm')) {
      audio.push(part.inlineData.data)
    }
  }
  if (msg.error) events.push(errorEvent(msg.error))
  return {
    events,
    audio,
    interrupted: content?.interrupted === true,
    goAway: msg.goAway !== undefined,
  }
}

export interface DecodedTranscription {
  events: LiveEvent[]
  /** True when an utterance starts, false when it ends; absent when the message says neither. */
  speaking?: boolean
  goAway: boolean
}

/**
 * One message from the transcription model. Each utterance comes back whole once it ends, with
 * no space before it, so it is set apart from the one before (the round trims the ends).
 */
export function decodeTranscription(msg: GeminiServerMessage): DecodedTranscription {
  const events: LiveEvent[] = []
  const heard = spoken(msg.serverContent?.inputTranscription?.text ?? '').trim()
  if (heard) events.push({ type: 'session.input_transcript.delta', delta: ` ${heard}` })
  if (msg.error) events.push(errorEvent(msg.error))
  const activity = msg.voiceActivity?.type
  return {
    events,
    speaking: activity === 'ACTIVITY_START' ? true : activity === 'ACTIVITY_END' ? false : undefined,
    goAway: msg.goAway !== undefined,
  }
}

function errorEvent(error: NonNullable<GeminiServerMessage['error']>): LiveEvent {
  return { type: 'error', error: { message: error.message ?? error.status ?? 'Gemini Live reported an error' } }
}

/** The client message that gives the coach text to act on, as its own user turn. */
export function textTurn(text: string): object {
  return { clientContent: { turns: [{ role: 'user', parts: [{ text }] }], turnComplete: true } }
}

/** One chunk of microphone audio. */
export function audioChunk(base64Pcm16k: string): object {
  return { realtimeInput: { audio: { data: base64Pcm16k, mimeType: 'audio/pcm;rate=16000' } } }
}

/** No more audio is coming: the transcription model finishes the utterance it is on right away. */
export function audioEnd(): object {
  return { realtimeInput: { audioStreamEnd: true } }
}

export function toBase64(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes)
  let binary = ''
  for (let i = 0; i < view.length; i += 0x8000) {
    binary += String.fromCharCode(...view.subarray(i, i + 0x8000))
  }
  return btoa(binary)
}

export function fromBase64(text: string): ArrayBuffer {
  const binary = atob(text)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}
