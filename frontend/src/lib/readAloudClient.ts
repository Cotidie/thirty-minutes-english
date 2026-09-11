// Browser side of one GPT-Live round over WebRTC: microphone in, coach audio
// out, JSON events on the "oai-events" data channel. Session creation goes
// through our backend, which holds the API key.

import { api } from '../api'
import type { LiveEvent } from './liveSession'

export interface ReadAloudConnection {
  /** Asks the coach for its closing remark (the paragraph is done). */
  finish(): void
  /** Ends the round. `session.closed` arrives through onEvent afterwards. */
  close(): void
  /** Drops everything without waiting for the final event. */
  dispose(): void
}

export interface ReadAloudOptions {
  paragraph: string
  audio: HTMLAudioElement
  onEvent: (event: LiveEvent) => void
  onDisconnect: () => void
}

const ICE_TIMEOUT_MS = 10_000
const FINISH_INSTRUCTION = 'The reader has finished. Give your closing now.'

export async function connectReadAloud(opts: ReadAloudOptions): Promise<ReadAloudConnection> {
  const peer = new RTCPeerConnection()
  let microphone: MediaStream | undefined
  let finalized = false

  const dispose = () => {
    microphone?.getTracks().forEach((t) => t.stop())
    events.close()
    peer.close()
    opts.audio.srcObject = null
  }

  peer.addEventListener('track', (e) => {
    opts.audio.srcObject = new MediaStream([e.track])
    opts.audio.play().catch(() => undefined)
  })

  // The data channel must exist before the offer is created.
  const events = peer.createDataChannel('oai-events')
  events.addEventListener('message', ({ data }) => {
    const event = JSON.parse(data) as LiveEvent
    if (event.type === 'session.closed') finalized = true
    opts.onEvent(event)
    if (event.type === 'session.closed') dispose()
  })
  events.addEventListener('close', () => {
    if (!finalized) {
      dispose()
      opts.onDisconnect()
    }
  })

  try {
    microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
    for (const track of microphone.getAudioTracks()) peer.addTrack(track, microphone)

    await peer.setLocalDescription(await peer.createOffer())
    await waitForIce(peer)
    const sdp = peer.localDescription?.sdp
    if (!sdp) throw new Error('Could not build a WebRTC offer')

    const result = await api.startReadAloud(opts.paragraph, sdp)
    await peer.setRemoteDescription({ type: 'answer', sdp: result.transport.sdp })
  } catch (e) {
    dispose()
    throw e
  }

  const send = (payload: object) => {
    if (events.readyState === 'open') events.send(JSON.stringify(payload))
  }

  return {
    finish: () =>
      send({
        type: 'session.instructions.append',
        event_id: 'finish',
        delegation_id: null,
        content: FINISH_INSTRUCTION,
      }),
    close: () => send({ type: 'session.close' }),
    dispose,
  }
}

function waitForIce(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      peer.removeEventListener('icegatheringstatechange', onChange)
      reject(new Error('Timed out gathering ICE candidates'))
    }, ICE_TIMEOUT_MS)
    function onChange() {
      if (peer.iceGatheringState !== 'complete') return
      clearTimeout(timer)
      peer.removeEventListener('icegatheringstatechange', onChange)
      resolve()
    }
    peer.addEventListener('icegatheringstatechange', onChange)
  })
}
