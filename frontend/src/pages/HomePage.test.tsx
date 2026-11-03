import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import { useCredits } from '../lib/credits'
import { creditsOf } from '../test/credits'
import { FakeEventSource } from '../test/fakeEventSource'
import type { SessionSummary } from '../types'
import { HomePage } from './HomePage'

vi.mock('../api', () => ({
  api: { listSessions: vi.fn(), topics: vi.fn(), listJobs: vi.fn(), deleteSession: vi.fn(), leaveSession: vi.fn() },
}))
vi.mock('../lib/credits', () => ({ useCredits: vi.fn() }))

const MINE: SessionSummary = { id: 7, created_at: '2026-10-30T10:00:00Z', topic: 'Trams', title: 'My trams', mine: true, shared_by: null }
const SHARED: SessionSummary = { id: 8, created_at: '2026-10-30T10:00:00Z', topic: 'Boats', title: 'Their boats', mine: false, shared_by: 'mina' }

function open() {
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.mocked(useCredits).mockReturnValue(creditsOf(340, { session: 200 }))
  vi.mocked(api.listSessions).mockReset().mockResolvedValue([])
  vi.mocked(api.topics).mockReset().mockResolvedValue({ topics: [], pending: false, error: null, labels: {} })
  vi.mocked(api.listJobs).mockReset().mockResolvedValue([])
  vi.mocked(api.deleteSession).mockReset().mockResolvedValue(undefined)
  vi.mocked(api.leaveSession).mockReset().mockResolvedValue(undefined)
})

test('everyone sees the topics and the price of a session', async () => {
  open()
  const button = await screen.findByRole('button', { name: 'Generate session' })
  expect(button).toBeEnabled()
  expect(button).toHaveTextContent('200')
  await waitFor(() => expect(api.topics).toHaveBeenCalled())
  expect(screen.getByText('Nothing yet. Sessions you make, and ones shared with you, appear here.')).toBeInTheDocument()
})

test('short of credits, the button is off and the page says what a session costs', async () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(120, { session: 200 }))
  open()
  const button = await screen.findByRole('button', { name: 'Generate session' })
  expect(button).toBeDisabled()
  expect(screen.getByText('120 credits left. A session costs 200. Ask the admin for more.')).toHaveAttribute('role', 'status')
  expect(button).toHaveAttribute('title', '120 credits left. A session costs 200. Ask the admin for more.')
})

test('the admin, who is not charged, sees no price', async () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(null, { session: 200 }))
  open()
  const button = await screen.findByRole('button', { name: 'Generate session' })
  expect(button).toBeEnabled()
  expect(button).not.toHaveTextContent('200')
})

test('my session can be deleted, and a shared one only taken off my list', async () => {
  vi.mocked(api.listSessions).mockResolvedValue([SHARED, MINE])
  open()
  expect(await screen.findByText('Shared by mina')).toBeInTheDocument()

  expect(screen.queryByRole('button', { name: 'Delete Their boats' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Remove Their boats from your list' }))
  expect(api.leaveSession).toHaveBeenCalledWith(8)
  expect(api.deleteSession).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.queryByText('Their boats')).not.toBeInTheDocument())

  await userEvent.click(screen.getByRole('button', { name: 'Delete My trams' }))
  expect(api.deleteSession).toHaveBeenCalledWith(7)
  await waitFor(() => expect(screen.queryByText('My trams')).not.toBeInTheDocument())
})

test('a session that cannot be deleted yet stays and says why', async () => {
  const why = 'This session is still being drawn. Cancel it on the progress bar: the session goes and half the price stays charged.'
  vi.mocked(api.listSessions).mockResolvedValue([MINE])
  vi.mocked(api.deleteSession).mockRejectedValue(new Error(why))
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Delete My trams' }))
  expect(await screen.findByText(why)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /My trams/ })).toBeInTheDocument()
})

test('a session shared while the page is open appears, and leaves when the share ends', async () => {
  open()
  expect(await screen.findByText('Nothing yet. Sessions you make, and ones shared with you, appear here.')).toBeInTheDocument()

  vi.mocked(api.listSessions).mockResolvedValue([SHARED])
  act(() => FakeEventSource.open[0].send('sessions'))
  expect(await screen.findByText('Shared by mina')).toBeInTheDocument()

  vi.mocked(api.listSessions).mockResolvedValue([])
  act(() => FakeEventSource.open[0].send('sessions'))
  await waitFor(() => expect(screen.queryByText('Shared by mina')).not.toBeInTheDocument())
})

test('a failed read says so, and the next good one clears it', async () => {
  vi.mocked(api.listSessions).mockRejectedValue(new Error('offline'))
  open()
  expect(await screen.findByText('Could not load past sessions: offline')).toBeInTheDocument()

  vi.mocked(api.listSessions).mockResolvedValue([SHARED])
  act(() => FakeEventSource.open[0].send('sessions'))
  expect(await screen.findByText('Shared by mina')).toBeInTheDocument()
  expect(screen.queryByText('Could not load past sessions: offline')).not.toBeInTheDocument()
})
