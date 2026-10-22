import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveEvent } from '../liveSession'
import { connectGeminiTranscription, FLUSH_TIMEOUT_MS } from './geminiWebsocket'

/** A socket that opens on its own and answers the setup; the test plays the server after that. */
class FakeSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static last: FakeSocket
  readyState = FakeSocket.CONNECTING
  sent: Record<string, unknown>[] = []
  private listeners: Record<string, ((e: unknown) => void)[]> = {}

  constructor() {
    FakeSocket.last = this
    queueMicrotask(() => {
      this.readyState = FakeSocket.OPEN
      this.fire('open', {})
    })
  }

  addEventListener(type: string, fn: (e: unknown) => void) {
    ;(this.listeners[type] ??= []).push(fn)
  }

  send(data: string) {
    const payload = JSON.parse(data)
    this.sent.push(payload)
    if (payload.setup) queueMicrotask(() => this.reply({ setupComplete: {} }))
  }

  close(_code?: number, reason = '') {
    if (this.readyState === FakeSocket.CLOSED) return
    this.readyState = FakeSocket.CLOSED
    this.fire('close', { reason })
  }

  reply(message: object) {
    this.fire('message', { data: JSON.stringify(message) })
  }

  private fire(type: string, e: unknown) {
    for (const fn of this.listeners[type] ?? []) fn(e)
  }
}

class FakeContext {
  audioWorklet = { addModule: async () => undefined }
  createMediaStreamDestination = () => ({ stream: {} })
  createMediaStreamSource = () => ({ connect: () => undefined })
  resume = async () => undefined
  close = async () => undefined
}

class FakeNode {
  static made: FakeNode[] = []
  port: { onmessage: ((e: { data: ArrayBuffer }) => void) | null; postMessage: () => void } = {
    onmessage: null,
    postMessage: () => undefined,
  }
  readonly name: string
  constructor(_context: unknown, name: string) {
    this.name = name
    FakeNode.made.push(this)
  }
  connect() {}
}

/** The microphone side: what it posts goes to the socket while the round is streaming. */
const recorder = () => FakeNode.made.findLast((node) => node.name === 'pcm-capture')!

/** Lets the socket's message chain run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
const audioEnds = () => FakeSocket.last.sent.filter((m) => JSON.stringify(m).includes('audioStreamEnd'))
const audioChunks = () => FakeSocket.last.sent.filter((m) => JSON.stringify(m).includes('audio/pcm'))

async function openRound(events: LiveEvent[]) {
  const round = await connectGeminiTranscription({
    start: async () => ({ provider: 'gemini', url: 'wss://live', setup: {} }) as never,
    audio: { srcObject: null, play: async () => undefined } as unknown as HTMLAudioElement,
    onEvent: (e) => events.push(e),
    onDisconnect: () => undefined,
  })
  return round
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('AudioContext', FakeContext)
  vi.stubGlobal('AudioWorkletNode', FakeNode)
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => undefined }] }) },
    configurable: true,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('Gemini transcription round', () => {
  it('on Done, ends the audio and waits for the sentence still being said before it closes', async () => {
    const events: LiveEvent[] = []
    const round = await openRound(events)
    recorder().port.onmessage!({ data: new ArrayBuffer(4) })
    FakeSocket.last.reply({ voiceActivity: { type: 'ACTIVITY_START' } })
    await settle()

    round.close()
    recorder().port.onmessage!({ data: new ArrayBuffer(4) })
    expect(audioEnds()).toHaveLength(1)
    expect(audioChunks()).toHaveLength(1) // nothing after the end
    expect(FakeSocket.last.readyState).toBe(FakeSocket.OPEN)

    FakeSocket.last.reply({ serverContent: { inputTranscription: { text: 'The survey was flawed.' } } })
    FakeSocket.last.reply({ voiceActivity: { type: 'ACTIVITY_END' } })
    await settle()
    expect(FakeSocket.last.readyState).toBe(FakeSocket.CLOSED)
    expect(events.filter((e) => e.type !== 'session.usage.updated')).toEqual([
      { type: 'session.started' },
      { type: 'session.input_transcript.delta', delta: ' The survey was flawed.' },
      { type: 'session.closed', usage: { seconds: 0 } },
    ])
  })

  it('closes at once when nobody is mid-sentence', async () => {
    const round = await openRound([])
    round.close()
    expect(audioEnds()).toHaveLength(1)
    expect(FakeSocket.last.readyState).toBe(FakeSocket.CLOSED)
  })

  it('closes anyway when the last sentence never comes back', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const round = await openRound([])
    FakeSocket.last.reply({ voiceActivity: { type: 'ACTIVITY_START' } })
    await vi.advanceTimersByTimeAsync(0)

    round.close()
    await vi.advanceTimersByTimeAsync(FLUSH_TIMEOUT_MS - 1)
    expect(FakeSocket.last.readyState).toBe(FakeSocket.OPEN)
    await vi.advanceTimersByTimeAsync(1)
    expect(FakeSocket.last.readyState).toBe(FakeSocket.CLOSED)
  })
})
