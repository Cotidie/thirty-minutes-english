// Gemini Live over WebSocket. The browser does the audio work itself: an
// AudioWorklet turns the microphone into 16 kHz PCM chunks for the socket,
// another plays the 24 kHz PCM that comes back through the same <audio>
// element the OpenAI path uses. The backend already minted the one-use token
// inside the URL and wrote the setup message. The same socket carries Summarize
// to the transcription model, which only writes down what it hears.

import type { Finding } from '../assessor/judge'
import type { LiveEvent } from '../liveSession'
import {
  audioChunk,
  audioEnd,
  decodeServerMessage,
  decodeTranscription,
  fromBase64,
  textTurn,
  toBase64,
  type GeminiServerMessage,
} from './geminiEvents'
import {
  correctionInstruction,
  sayInstruction,
  type LiveConnection,
  type LiveOptions,
} from './transport'

const CAPTURE_RATE = 16_000
const PLAYBACK_RATE = 24_000
const SETUP_TIMEOUT_MS = 10_000
const TICK_MS = 1000
/** How long Done waits for the sentence still being said before it closes anyway. */
export const FLUSH_TIMEOUT_MS = 3000

export function connectGemini(opts: LiveOptions): Promise<LiveConnection> {
  return join(new GeminiRound(opts), opts)
}

/** Summarize's round on the transcription model: nothing is said back, and Done keeps the last sentence. */
export function connectGeminiTranscription(opts: LiveOptions): Promise<LiveConnection> {
  return join(new GeminiTranscription(opts), opts)
}

async function join(round: GeminiRound, opts: LiveOptions): Promise<LiveConnection> {
  const session = await opts.start()
  if (session.provider !== 'gemini') throw new Error(`Expected a Gemini session, got ${session.provider}`)
  try {
    await round.open(session.url, session.setup)
  } catch (e) {
    round.dispose()
    throw e
  }
  return round
}

class GeminiRound implements LiveConnection {
  microphone!: MediaStream
  private socket!: WebSocket
  private capture!: AudioContext
  private playback!: AudioContext
  private player!: AudioWorkletNode
  private startedAt = 0
  private ticker: ReturnType<typeof setInterval> | null = null
  /** Set once the round is over on purpose: a socket close is then the end, not a drop. */
  protected finalized = false
  /** Microphone audio goes to the socket until this is cleared. */
  protected streaming = true
  private disposed = false
  /** Server messages come as Blobs; decoding in order needs a chain. */
  private inbox: Promise<void> = Promise.resolve()

  private readonly opts: LiveOptions

  constructor(opts: LiveOptions) {
    this.opts = opts
  }

  async open(url: string, setup: Record<string, unknown>): Promise<void> {
    this.microphone = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    this.capture = new AudioContext({ sampleRate: CAPTURE_RATE })
    this.playback = new AudioContext({ sampleRate: PLAYBACK_RATE })
    await Promise.all([
      this.capture.audioWorklet.addModule('/worklets/pcm-capture.js'),
      this.playback.audioWorklet.addModule('/worklets/pcm-player.js'),
    ])

    this.player = new AudioWorkletNode(this.playback, 'pcm-player')
    const speaker = this.playback.createMediaStreamDestination()
    this.player.connect(speaker)
    this.opts.audio.srcObject = speaker.stream
    this.opts.audio.play().catch(() => undefined)

    this.socket = new WebSocket(url)
    await this.handshake(setup)

    const mic = this.capture.createMediaStreamSource(this.microphone)
    const recorder = new AudioWorkletNode(this.capture, 'pcm-capture')
    recorder.port.onmessage = ({ data }) => {
      if (this.streaming) this.send(audioChunk(toBase64(data as ArrayBuffer)))
    }
    mic.connect(recorder)
    await Promise.all([this.capture.resume(), this.playback.resume()])

    this.startedAt = Date.now()
    this.ticker = setInterval(() => this.emit({ type: 'session.usage.updated', usage: { seconds: this.seconds() } }), TICK_MS)
    this.emit({ type: 'session.started' })
  }

  /** Sends the setup on open and resolves on setupComplete; anything else first is a failure. */
  private handshake(setup: Record<string, unknown>): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Gemini Live did not answer the setup in time')), SETUP_TIMEOUT_MS)
      let ready = false
      const fail = (reason: string) => {
        clearTimeout(timer)
        reject(new Error(reason))
      }
      this.socket.addEventListener('open', () => this.socket.send(JSON.stringify({ setup })))
      this.socket.addEventListener('error', () => {
        if (!ready) fail('Could not reach Gemini Live')
      })
      this.socket.addEventListener('close', (e) => {
        if (!ready) return fail(e.reason ? `Gemini Live closed the socket: ${e.reason}` : 'Gemini Live closed the socket')
        this.onClose(e)
      })
      this.socket.addEventListener('message', (e) => {
        this.inbox = this.inbox.then(async () => {
          const msg = JSON.parse(typeof e.data === 'string' ? e.data : await (e.data as Blob).text()) as GeminiServerMessage
          if (!ready) {
            if (!msg.setupComplete) return fail(msg.error?.message ?? 'Gemini Live rejected the setup')
            ready = true
            clearTimeout(timer)
            resolve()
            return
          }
          this.receive(msg)
        })
      })
    })
  }

  protected receive(msg: GeminiServerMessage): void {
    const { events, audio, interrupted, goAway } = decodeServerMessage(msg)
    if (interrupted) this.player.port.postMessage({ type: 'flush' })
    for (const chunk of audio) this.player.port.postMessage(fromBase64(chunk))
    for (const event of events) this.emit(event)
    if (goAway) this.finalized = true
  }

  private onClose(e: CloseEvent): void {
    if (this.disposed) return
    const seconds = this.seconds()
    if (this.finalized) {
      this.emit({ type: 'session.closed', usage: { seconds } })
      this.dispose()
      return
    }
    if (e.reason) this.emit({ type: 'error', error: { message: e.reason } })
    this.dispose()
    this.opts.onDisconnect()
  }

  private seconds(): number {
    return this.startedAt ? Math.round((Date.now() - this.startedAt) / 1000) : 0
  }

  protected emit(event: LiveEvent): void {
    if (!this.disposed) this.opts.onEvent(event)
  }

  protected send(payload: object): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload))
  }

  say(text: string): void {
    this.send(textTurn(sayInstruction(text)))
  }

  correct(finding: Finding): void {
    this.send(textTurn(correctionInstruction(finding)))
  }

  close(): void {
    if (this.finalized) return
    this.finalized = true
    if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
      this.socket.close(1000, 'round over')
    } else {
      this.onClose(new CloseEvent('close'))
    }
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    if (this.ticker) clearInterval(this.ticker)
    this.microphone?.getTracks().forEach((t) => t.stop())
    if (this.socket && this.socket.readyState !== WebSocket.CLOSED) this.socket.close()
    void this.capture?.close().catch(() => undefined)
    void this.playback?.close().catch(() => undefined)
    this.opts.audio.srcObject = null
  }
}

/**
 * Gemini's transcription model. It says nothing; each utterance comes back whole once it ends.
 * Done ends the audio first, so the sentence still being said comes back before the socket closes.
 */
class GeminiTranscription extends GeminiRound {
  private speaking = false
  private flushed: (() => void) | null = null

  protected receive(msg: GeminiServerMessage): void {
    const { events, speaking, goAway } = decodeTranscription(msg)
    for (const event of events) this.emit(event)
    if (goAway) this.finalized = true
    if (speaking !== undefined) this.speaking = speaking
    if (!this.speaking) this.flushed?.()
  }

  close(): void {
    if (!this.streaming) return
    this.streaming = false
    this.send(audioEnd())
    if (!this.speaking) return super.close()
    const timer = setTimeout(() => this.flushed?.(), FLUSH_TIMEOUT_MS)
    this.flushed = () => {
      clearTimeout(timer)
      this.flushed = null
      super.close()
    }
  }
}
