// Pure translation of one Gemini Live server message into the events the
// rest of the app already understands (the OpenAI names), plus the audio
// chunks and turn signals the transport itself acts on.

import type { LiveEvent } from '../liveSession'

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
    turnComplete?: boolean
    interrupted?: boolean
    generationComplete?: boolean
  }
  goAway?: { timeLeft?: string }
  error?: { message?: string; status?: string }
}

export interface Decoded {
  events: LiveEvent[]
  /** Base64 16-bit PCM at 24 kHz, in order. */
  audio: string[]
  /** The user spoke over the coach: drop whatever is still queued to play. */
  interrupted: boolean
  /** The coach has said everything it will for this turn. */
  turnComplete: boolean
  /** The server will close the socket soon; the close that follows is not a drop. */
  goAway: boolean
}

/** Gemini's transcription marks a silent turn or plain noise with a tag; neither is speech. */
const TRANSCRIPT_MARKERS = /<(?:no speech|noise|silence)>/gi

export function spoken(text: string): string {
  return text.replace(TRANSCRIPT_MARKERS, '')
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
  if (msg.error) {
    events.push({ type: 'error', error: { message: msg.error.message ?? msg.error.status ?? 'Gemini Live reported an error' } })
  }
  return {
    events,
    audio,
    interrupted: content?.interrupted === true,
    turnComplete: content?.turnComplete === true,
    goAway: msg.goAway !== undefined,
  }
}

/** The client message that gives the coach text to act on, as its own user turn. */
export function textTurn(text: string): object {
  return { clientContent: { turns: [{ role: 'user', parts: [{ text }] }], turnComplete: true } }
}

/** One chunk of microphone audio. */
export function audioChunk(base64Pcm16k: string): object {
  return { realtimeInput: { audio: { data: base64Pcm16k, mimeType: 'audio/pcm;rate=16000' } } }
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
