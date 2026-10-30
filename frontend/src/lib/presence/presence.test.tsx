import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test } from 'vitest'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { PresenceProvider } from './PresenceProvider'
import { useSharedView } from './useSharedView'

const WELCOME = { type: 'welcome', you: { id: 'me', color: 0 }, people: [], view: {}, timer: null }

function Chip() {
  const [on, setOn] = useSharedView<boolean>('chip:word:2', false)
  return <button onClick={() => setOn(!on)}>{on ? 'on' : 'off'}</button>
}

function inARoom() {
  render(
    <PresenceProvider sessionId={7}>
      <Chip />
    </PresenceProvider>,
  )
  return FakeWebSocket.only
}

beforeEach(() => {
  FakeWebSocket.instances = []
})

test('connects once to the session with no buffer, and closes on leaving', () => {
  const { unmount } = render(
    <PresenceProvider sessionId={7}>
      <p />
    </PresenceProvider>,
  )
  expect(FakeWebSocket.open.map((s) => s.url)).toEqual(['ws://localhost:3000/api/sessions/7/presence'])
  expect(FakeWebSocket.open[0].options.maxEnqueuedMessages).toBe(0)
  unmount()
  expect(FakeWebSocket.open).toHaveLength(0)
})

test.each([4401, 4403, 4404])('closed with %i it stops trying', (code) => {
  const socket = inARoom()
  act(() => socket.drop(code))
  expect(FakeWebSocket.open).toHaveLength(0)
})

test('dropped for any other reason it keeps trying', () => {
  const socket = inARoom()
  act(() => socket.drop(1006))
  expect(FakeWebSocket.open).toHaveLength(1)
})

test('useSharedView is plain local state without a provider', async () => {
  render(<Chip />)
  await userEvent.click(screen.getByRole('button', { name: 'off' }))
  expect(screen.getByRole('button', { name: 'on' })).toBeInTheDocument()
  expect(FakeWebSocket.open).toHaveLength(0)
})

test('useSharedView shows what arrives and sends what I set', async () => {
  const socket = inARoom()
  act(() => {
    socket.connect()
    socket.receive(WELCOME)
    socket.receive({ type: 'view', key: 'chip:word:2', value: true, by: 'b', seq: 1 })
  })
  const chip = screen.getByRole('button', { name: 'on' })
  expect(socket.sent).toEqual([])
  await userEvent.click(chip)
  expect(screen.getByRole('button', { name: 'off' })).toBeInTheDocument()
  expect(socket.sent).toEqual([{ type: 'view', key: 'chip:word:2', value: false, seq: expect.any(Number) }])
})

test('someone coming in late sees what is already turned over', () => {
  const socket = inARoom()
  act(() => {
    socket.connect()
    socket.receive({ ...WELCOME, view: { 'chip:word:2': true } })
  })
  expect(screen.getByRole('button', { name: 'on' })).toBeInTheDocument()
})

test('a set while the socket is down stays on my screen and sends nothing', async () => {
  const socket = inARoom()
  await userEvent.click(screen.getByRole('button', { name: 'off' }))
  expect(screen.getByRole('button', { name: 'on' })).toBeInTheDocument()
  expect(socket.sent).toEqual([])
})
