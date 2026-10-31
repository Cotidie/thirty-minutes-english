import { WebSocket as ReconnectingWebSocket } from 'partysocket'
import type { PresenceStore, ServerMessage } from './store'

/** No login, another origin, no access: trying again would only be refused again. */
const REFUSED = new Set([4401, 4403, 4404])

function presenceUrl(sessionId: number): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/api/sessions/${sessionId}/presence`
}

/**
 * The only place that opens this socket. Nothing is queued while it is down: a cursor from then is out of date, and at
 * every welcome the store says again where this screen stands. Returns how to close it.
 */
export function connectPresence(sessionId: number, store: PresenceStore): () => void {
  const socket = new ReconnectingWebSocket(presenceUrl(sessionId), undefined, { maxEnqueuedMessages: 0 })
  store.attach((message) => {
    if (socket.readyState === socket.OPEN) socket.send(JSON.stringify(message))
  })
  socket.addEventListener('message', (event) => store.receive(JSON.parse(event.data as string) as ServerMessage))
  socket.addEventListener('close', (event) => {
    if (REFUSED.has(event.code)) socket.close()
  })
  return () => {
    store.attach(null)
    socket.close()
  }
}
