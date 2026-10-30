import { act, render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { PresenceProvider } from '../lib/presence/PresenceProvider'
import { FakeWebSocket } from './fakeWebSocket'

export const WELCOME = { type: 'welcome', you: { id: 'me', color: 0 }, people: [], view: {}, timer: null }

/** Renders inside a session whose socket is up, with nobody else in it yet. */
export function renderInRoom(ui: ReactElement, welcome: object = WELCOME) {
  const rendered = render(<PresenceProvider sessionId={3}>{ui}</PresenceProvider>)
  const socket = FakeWebSocket.only
  act(() => {
    socket.connect()
    socket.receive(welcome)
  })
  return { ...rendered, socket }
}

/** Someone else in the session sets this. */
export function someoneSets(socket: FakeWebSocket, key: string, value: unknown) {
  act(() => socket.receive({ type: 'view', key, value, by: 'someone', seq: 1 }))
}

export function viewsSent(socket: FakeWebSocket) {
  return socket.sent.filter((message) => message.type === 'view').map(({ key, value }) => ({ key, value }))
}
