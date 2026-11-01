import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api'
import type { LiveEvent } from '../liveSession'
import { connectGemini, connectGeminiTranscription, FLUSH_TIMEOUT_MS } from './geminiWebsocket'
import type { LiveOptions } from './transport'

vi.mock('../../api', () => ({ api: { confirmHold: vi.fn(async () => undefined), giveBackHold: vi.fn(async () => undefined) } }))

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
    start: async () => ({ url: 'wss://live', setup: {}, hold: null }),
    audio: { srcObject: null, play: async () => undefined } as unknown as HTMLAudioElement,
    onEvent: (e) => events.push(e),
    onDisconnect: () => undefined,
  })
  return round
}

beforeEach(() => {
  vi.mocked(api.confirmHold).mockClear()
  vi.mocked(api.giveBackHold).mockClear()
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

const HOLD = 31
const options = (over: Partial<LiveOptions> = {}): LiveOptions => ({
  start: vi.fn(async () => ({ url: 'wss://live', setup: {}, hold: HOLD })),
  audio: { srcObject: null, play: async () => undefined } as unknown as HTMLAudioElement,
  onEvent: () => undefined,
  onDisconnect: () => undefined,
  ...over,
})

/** A socket whose server turns the setup down. */
class RefusingSocket extends FakeSocket {
  send() {
    queueMicrotask(() => this.reply({ error: { message: 'no' } }))
  }
}

const microphoneAnswers = (getUserMedia: () => Promise<unknown>) =>
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true })

describe('what a round pays', () => {
  it('asks for the microphone before it asks for a token', async () => {
    const order: string[] = []
    microphoneAnswers(async () => {
      order.push('microphone')
      return { getTracks: () => [] }
    })
    const start = async () => {
      order.push('token')
      return { url: 'wss://live', setup: {}, hold: HOLD }
    }
    await connectGemini(options({ start }))
    expect(order).toEqual(['microphone', 'token'])
  })

  it('takes no token when the microphone is refused', async () => {
    microphoneAnswers(async () => {
      throw new Error('Permission denied')
    })
    const opts = options()
    await expect(connectGemini(opts)).rejects.toThrow('Permission denied')
    expect(opts.start).not.toHaveBeenCalled()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('confirms once the setup is answered', async () => {
    await connectGemini(options())
    expect(api.confirmHold).toHaveBeenCalledExactlyOnceWith(HOLD)
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('gives the price back when the setup is refused', async () => {
    vi.stubGlobal('WebSocket', RefusingSocket)
    await expect(connectGemini(options())).rejects.toThrow('no')
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(HOLD)
    expect(api.confirmHold).not.toHaveBeenCalled()
  })

  it('gives the price back when the connection drops, once however often it is asked', async () => {
    const onDisconnect = vi.fn()
    const round = await connectGemini(options({ onDisconnect }))
    FakeSocket.last.close(1006, '')
    round.giveBack()
    expect(onDisconnect).toHaveBeenCalledOnce()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(HOLD)
  })

  it('keeps the price when the round ends on purpose', async () => {
    const round = await connectGemini(options())
    round.close()
    await settle()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('reports nothing once the round is disposed, as Retry does', async () => {
    const round = await connectGemini(options())
    round.dispose()
    await settle()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('takes no token when it is abandoned at the microphone', async () => {
    const leaving = new AbortController()
    microphoneAnswers(async () => {
      leaving.abort()
      return { getTracks: () => [{ stop: () => undefined }] }
    })
    const opts = options({ signal: leaving.signal })
    await expect(connectGemini(opts)).rejects.toThrow()
    expect(opts.start).not.toHaveBeenCalled()
  })

  it('gives the price back when it is abandoned while the token comes', async () => {
    const leaving = new AbortController()
    const start = vi.fn(async () => {
      leaving.abort()
      return { url: 'wss://live', setup: {}, hold: HOLD }
    })
    await expect(connectGemini(options({ start, signal: leaving.signal }))).rejects.toThrow()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(HOLD)
    expect(api.confirmHold).not.toHaveBeenCalled()
  })

  it('sends nothing for the admin, whose round has no hold', async () => {
    const start = async () => ({ url: 'wss://live', setup: {}, hold: null })
    const round = await connectGemini(options({ start }))
    FakeSocket.last.close(1006, '')
    round.giveBack()
    expect(api.confirmHold).not.toHaveBeenCalled()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })
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
