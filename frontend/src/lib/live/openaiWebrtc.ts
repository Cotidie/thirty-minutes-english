// OpenAI GPT-Live over WebRTC: microphone track out, coach track in, JSON
// events on the "oai-events" data channel. The backend answers our offer.

import type { LiveEvent } from '../liveSession'
import {
  CONFIRM_INSTRUCTION,
  FINISH_INSTRUCTION,
  correctionInstruction,
  reviewInstruction,
  sayInstruction,
  type LiveConnection,
  type LiveOptions,
} from './transport'

const ICE_TIMEOUT_MS = 10_000

export async function connectOpenAI(opts: LiveOptions): Promise<LiveConnection> {
  const peer = new RTCPeerConnection()
  let microphone: MediaStream | undefined
  let finalized = false
  let disposed = false

  const dispose = () => {
    disposed = true
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
    // A close we caused (dispose after an error or session.closed) is not a drop.
    if (finalized || disposed) return
    dispose()
    opts.onDisconnect()
  })

  try {
    microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
    for (const track of microphone.getAudioTracks()) peer.addTrack(track, microphone)

    await peer.setLocalDescription(await peer.createOffer())
    await waitForIce(peer)
    const sdp = peer.localDescription?.sdp
    if (!sdp) throw new Error('Could not build a WebRTC offer')

    const result = await opts.start(sdp)
    if (result.provider !== 'openai') throw new Error(`Expected an OpenAI session, got ${result.provider}`)
    await peer.setRemoteDescription({ type: 'answer', sdp: result.transport.sdp })
  } catch (e) {
    dispose()
    throw e
  }

  const send = (payload: object) => {
    if (events.readyState === 'open') events.send(JSON.stringify(payload))
  }

  const instruct = (eventId: string, content: string) =>
    send({ type: 'session.instructions.append', event_id: eventId, delegation_id: null, content })

  return {
    microphone,
    finish: () => instruct('finish', FINISH_INSTRUCTION),
    say: (text) => instruct('say', sayInstruction(text)),
    correct: (finding) => instruct('correct', correctionInstruction(finding)),
    confirm: () => instruct('confirm', CONFIRM_INSTRUCTION),
    review: (findings) => instruct('review', reviewInstruction(findings)),
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
