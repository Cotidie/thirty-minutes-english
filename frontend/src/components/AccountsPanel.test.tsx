import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import type { Account } from '../types'
import { AccountsPanel } from './AccountsPanel'

vi.mock('../api', () => ({ api: { listAccounts: vi.fn(), accountCredits: vi.fn(), grantCredits: vi.fn() } }))

const ADMIN = { id: 1, email: 'boss@example.com', username: 'boss', is_admin: true, created_at: '2026-10-30T10:00:00Z', credits: null }
const MINA = { id: 2, email: 'mina@example.com', username: '미나', is_admin: false, created_at: '2026-10-31T10:00:00Z', credits: 340 }

beforeEach(() => {
  vi.mocked(api.listAccounts).mockReset().mockResolvedValue([ADMIN, MINA])
  vi.mocked(api.accountCredits).mockReset().mockResolvedValue([])
  vi.mocked(api.grantCredits).mockReset()
})

test('each account shows its balance; the admin is not charged', async () => {
  render(<AccountsPanel />)
  expect(await screen.findByText('340')).toBeInTheDocument()
  expect(screen.getByText('미나')).toBeInTheDocument()
  expect(screen.getByText('not charged')).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('spinbutton', { name: 'boss@example.com credits to add' })).not.toBeInTheDocument()
  await waitFor(() => expect(api.accountCredits).toHaveBeenCalledWith(2))
  expect(api.accountCredits).toHaveBeenCalledTimes(1)
})

test('each account shows what it last spent', async () => {
  vi.mocked(api.accountCredits).mockResolvedValue([{ at: '2026-11-01T09:00:00Z', amount: -200, kind: 'session', detail: 'Trams' }])
  render(<AccountsPanel />)
  const history = await screen.findByRole('list', { name: 'mina@example.com recent charges' })
  expect(within(history).getByRole('listitem')).toHaveTextContent('Session')
  expect(within(history).getByRole('listitem')).toHaveTextContent('Trams')
  expect(within(history).getByRole('listitem')).toHaveTextContent('−200')
})

test('credits taken back read as taken back by you', async () => {
  vi.mocked(api.accountCredits).mockResolvedValue([{ at: '2026-11-01T09:00:00Z', amount: -34, kind: 'grant', detail: null }])
  render(<AccountsPanel />)
  const history = await screen.findByRole('list', { name: 'mina@example.com recent charges' })
  expect(within(history).getByRole('listitem')).toHaveTextContent('Taken back by you')
})

test('adding credits saves at once and shows the new balance and the row it made', async () => {
  vi.mocked(api.grantCredits).mockResolvedValue({ ...MINA, credits: 540 })
  vi.mocked(api.accountCredits).mockResolvedValueOnce([]).mockResolvedValueOnce([{ at: '2026-11-01T09:00:00Z', amount: 200, kind: 'grant', detail: null }])
  render(<AccountsPanel />)
  const field = await screen.findByRole('spinbutton', { name: 'mina@example.com credits to add' })
  expect(field).toHaveValue(200)
  await userEvent.click(screen.getByRole('button', { name: 'Add credits to mina@example.com' }))
  expect(api.grantCredits).toHaveBeenCalledWith(2, 200)
  expect(await screen.findByText('540')).toBeInTheDocument()
  const history = await screen.findByRole('list', { name: 'mina@example.com recent charges' })
  expect(within(history).getByRole('listitem')).toHaveTextContent('Added by you')
  expect(within(history).getByRole('listitem')).toHaveTextContent('+200')
})

test('a negative number takes credits back, and zero is refused before it is sent', async () => {
  vi.mocked(api.grantCredits).mockResolvedValue({ ...MINA, credits: 240 })
  render(<AccountsPanel />)
  const field = await screen.findByRole('spinbutton', { name: 'mina@example.com credits to add' })
  await userEvent.clear(field)
  await userEvent.type(field, '0')
  await userEvent.click(screen.getByRole('button', { name: 'Add credits to mina@example.com' }))
  expect(api.grantCredits).not.toHaveBeenCalled()
  expect(screen.getByRole('alert')).toHaveTextContent('Enter a number other than 0.')
  await userEvent.clear(field)
  await userEvent.type(field, '-100')
  await userEvent.click(screen.getByRole('button', { name: 'Add credits to mina@example.com' }))
  expect(api.grantCredits).toHaveBeenCalledWith(2, -100)
  expect(await screen.findByText('240')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('an empty field or a fraction is refused the same way', async () => {
  render(<AccountsPanel />)
  const field = await screen.findByRole('spinbutton', { name: 'mina@example.com credits to add' })
  await userEvent.clear(field)
  await userEvent.click(screen.getByRole('button', { name: 'Add credits to mina@example.com' }))
  await userEvent.type(field, '1.5')
  await userEvent.click(screen.getByRole('button', { name: 'Add credits to mina@example.com' }))
  expect(api.grantCredits).not.toHaveBeenCalled()
  expect(screen.getByRole('alert')).toHaveTextContent('Enter a number other than 0.')
})

test('Enter in the field adds', async () => {
  vi.mocked(api.grantCredits).mockResolvedValue({ ...MINA, credits: 540 })
  render(<AccountsPanel />)
  const field = await screen.findByRole('spinbutton', { name: 'mina@example.com credits to add' })
  await userEvent.type(field, '{Enter}')
  expect(api.grantCredits).toHaveBeenCalledWith(2, 200)
  expect(await screen.findByText('540')).toBeInTheDocument()
})

test('a second press while the first is on its way adds nothing more', async () => {
  let saved: (account: Account) => void = () => undefined
  vi.mocked(api.grantCredits).mockReturnValue(new Promise((resolve) => (saved = resolve)))
  render(<AccountsPanel />)
  await screen.findByText('340')
  const add = screen.getByRole('button', { name: 'Add credits to mina@example.com' })
  await userEvent.click(add)
  await userEvent.click(add)
  expect(api.grantCredits).toHaveBeenCalledTimes(1)
  saved({ ...MINA, credits: 540 })
  expect(await screen.findByText('540')).toBeInTheDocument()
  expect(add).toBeEnabled()
})

test('a failed grant says why and leaves the balance', async () => {
  vi.mocked(api.grantCredits).mockRejectedValue(new Error('offline'))
  render(<AccountsPanel />)
  await screen.findByText('340')
  await userEvent.click(screen.getByRole('button', { name: 'Add credits to mina@example.com' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('offline')
  expect(screen.getByText('340')).toBeInTheDocument()
})

test('a list that will not load says why', async () => {
  vi.mocked(api.listAccounts).mockRejectedValue(new Error('offline'))
  render(<AccountsPanel />)
  expect(await screen.findByRole('alert')).toHaveTextContent('offline')
})
