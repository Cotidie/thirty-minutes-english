import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import { useAuth } from '../lib/auth'
import type { Me, SessionSummary } from '../types'
import { HomePage } from './HomePage'

vi.mock('../api', () => ({
  api: { listSessions: vi.fn(), topics: vi.fn(), listJobs: vi.fn(), deleteSession: vi.fn(), leaveSession: vi.fn() },
}))
vi.mock('../lib/auth', () => ({ useAuth: vi.fn() }))

const NEWCOMER: Me = { id: 1, email: 'a@example.com', is_admin: false, can_create: false }
const MINE: SessionSummary = { id: 7, created_at: '2026-10-30T10:00:00Z', topic: 'Trams', title: 'My trams', mine: true, shared_by: null }
const SHARED: SessionSummary = { id: 8, created_at: '2026-10-30T10:00:00Z', topic: 'Boats', title: 'Their boats', mine: false, shared_by: 'mina@example.com' }

function logIn(me: Me) {
  vi.mocked(useAuth).mockReturnValue({ me, loading: false, logIn: vi.fn(), signUp: vi.fn(), logOut: vi.fn() })
}

function open() {
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.listSessions).mockReset().mockResolvedValue([])
  vi.mocked(api.topics).mockReset().mockResolvedValue({ topics: [], pending: false, error: null, labels: {} })
  vi.mocked(api.listJobs).mockReset().mockResolvedValue([])
  vi.mocked(api.deleteSession).mockReset().mockResolvedValue(undefined)
  vi.mocked(api.leaveSession).mockReset().mockResolvedValue(undefined)
})

test('an account that may not create sees why, and asks for no topics', async () => {
  logIn(NEWCOMER)
  open()
  expect(await screen.findByText("Session creation isn't on for this account yet. Ask the admin to turn it on.")).toBeInTheDocument()
  expect(screen.getByText('Nothing here yet. Sessions shared with you appear here.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Generate session' })).not.toBeInTheDocument()
  expect(api.topics).not.toHaveBeenCalled()
  expect(api.listJobs).not.toHaveBeenCalled()
})

test.each([
  ['approved', { ...NEWCOMER, can_create: true }],
  ['the admin', { ...NEWCOMER, is_admin: true }],
])('%s can create', async (_who, me) => {
  logIn(me)
  open()
  expect(await screen.findByRole('button', { name: 'Generate session' })).toBeInTheDocument()
  await waitFor(() => expect(api.topics).toHaveBeenCalled())
  expect(screen.queryByText(/Session creation isn't on/)).not.toBeInTheDocument()
})

test('my session can be deleted, and a shared one only taken off my list', async () => {
  logIn(NEWCOMER)
  vi.mocked(api.listSessions).mockResolvedValue([SHARED, MINE])
  open()
  expect(await screen.findByText('Shared by mina@example.com')).toBeInTheDocument()

  expect(screen.queryByRole('button', { name: 'Delete Their boats' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Remove Their boats from your list' }))
  expect(api.leaveSession).toHaveBeenCalledWith(8)
  expect(api.deleteSession).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.queryByText('Their boats')).not.toBeInTheDocument())

  await userEvent.click(screen.getByRole('button', { name: 'Delete My trams' }))
  expect(api.deleteSession).toHaveBeenCalledWith(7)
  await waitFor(() => expect(screen.queryByText('My trams')).not.toBeInTheDocument())
})
