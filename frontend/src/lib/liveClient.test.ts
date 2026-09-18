import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { connectAsk, connectReadAloud } from './liveClient'

vi.mock('../api', () => ({
  api: { startReadAloud: vi.fn(), startPhrase: vi.fn(), voiceProvider: vi.fn(async () => 'openai') },
}))

// Minimal WebRTC stand-ins: enough to run the offer path and fire channel events.
class FakeChannel extends EventTarget {
  readyState = 'open'
  send = vi.fn()
  close() {
    this.readyState = 'closed'
    queueMicrotask(() => this.dispatchEvent(new Event('close')))
  }
}

let lastPeer: FakePeer

class FakePeer extends EventTarget {
  constructor() {
    super()
    lastPeer = this
  }
  iceGatheringState = 'complete'
  localDescription = { sdp: 'v=0 offer' }
  channel = new FakeChannel()
  createDataChannel = () => this.channel
  addTrack = vi.fn()
  createOffer = async () => ({ type: 'offer', sdp: 'v=0 offer' })
  setLocalDescription = async () => undefined
  setRemoteDescription = vi.fn(async () => undefined)
  close = vi.fn()
}

beforeEach(() => {
  vi.stubGlobal('RTCPeerConnection', FakePeer)
  vi.stubGlobal('MediaStream', class {})
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: async () => ({ getAudioTracks: () => [], getTracks: () => [] }) },
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('connectReadAloud', () => {
  it('surfaces the backend error and does not report a dropped connection', async () => {
    vi.mocked(api.startReadAloud).mockRejectedValueOnce(new Error('read-aloud is off: set OPENAI_API_KEY on the backend'))
    const onDisconnect = vi.fn()
    const audio = { play: async () => undefined } as unknown as HTMLAudioElement

    await expect(connectReadAloud('p', { audio, onEvent: vi.fn(), onDisconnect })).rejects.toThrow(
      'set OPENAI_API_KEY',
    )
    await new Promise((r) => setTimeout(r, 0))
    expect(onDisconnect).not.toHaveBeenCalled()
  })

  it('applies the answer, forwards events, and reports a drop only when the channel closes early', async () => {
    vi.mocked(api.startReadAloud).mockResolvedValueOnce({
      provider: 'openai',
      session: { id: 'live_1' },
      transport: { type: 'webrtc', sdp: 'v=0 answer' },
    })
    const onEvent = vi.fn()
    const onDisconnect = vi.fn()
    const audio = { play: async () => undefined } as unknown as HTMLAudioElement

    const conn = await connectReadAloud('p', { audio, onEvent, onDisconnect })
    expect(vi.mocked(api.startReadAloud)).toHaveBeenCalledWith('p', 'v=0 offer')
    expect(lastPeer.setRemoteDescription).toHaveBeenCalledWith({ type: 'answer', sdp: 'v=0 answer' })

    const channel = lastPeer.channel
    channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'session.started' }) }))
    expect(onEvent).toHaveBeenCalledWith({ type: 'session.started' })

    conn.finish()
    conn.close()
    expect(channel.send.mock.calls.map(([raw]) => JSON.parse(raw).type)).toEqual([
      'session.instructions.append',
      'session.close',
    ])

    // Server drops the channel with no final event: that is a disconnect.
    channel.dispatchEvent(new Event('close'))
    expect(onDisconnect).toHaveBeenCalledTimes(1)
    expect(lastPeer.close).toHaveBeenCalled()
  })

  it('treats the close after session.closed as normal', async () => {
    vi.mocked(api.startReadAloud).mockResolvedValueOnce({
      provider: 'openai',
      session: { id: 'live_1' },
      transport: { type: 'webrtc', sdp: 'v=0 answer' },
    })
    const onDisconnect = vi.fn()
    const audio = { play: async () => undefined } as unknown as HTMLAudioElement
    await connectReadAloud('p', { audio, onEvent: vi.fn(), onDisconnect })

    lastPeer.channel.dispatchEvent(
      new MessageEvent('message', { data: JSON.stringify({ type: 'session.closed', usage: { seconds: 3 } }) }),
    )
    await new Promise((r) => setTimeout(r, 0))
    expect(onDisconnect).not.toHaveBeenCalled()
  })
})

describe('connectAsk', () => {
  it('starts a phrase session with the topic and shares the round plumbing', async () => {
    vi.mocked(api.startPhrase).mockResolvedValueOnce({
      provider: 'openai',
      session: { id: 'live_2' },
      transport: { type: 'webrtc', sdp: 'v=0 answer' },
    })
    const onEvent = vi.fn()
    const audio = { play: async () => undefined } as unknown as HTMLAudioElement

    const conn = await connectAsk('Digital twins', { audio, onEvent, onDisconnect: vi.fn() })
    expect(vi.mocked(api.startPhrase)).toHaveBeenCalledWith('Digital twins', 'v=0 offer')

    const channel = lastPeer.channel
    channel.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'session.started' }) }))
    expect(onEvent).toHaveBeenCalledWith({ type: 'session.started' })

    conn.close()
    expect(JSON.parse(channel.send.mock.calls[0][0]).type).toBe('session.close')
  })
})
