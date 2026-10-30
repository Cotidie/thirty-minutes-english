import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import { AccountsPanel } from './AccountsPanel'

vi.mock('../api', () => ({ api: { listAccounts: vi.fn(), setCanCreate: vi.fn() } }))

const ADMIN = { id: 1, email: 'boss@example.com', is_admin: true, can_create: false, created_at: '2026-10-30T10:00:00Z' }
const MINA = { id: 2, email: 'mina@example.com', is_admin: false, can_create: false, created_at: '2026-10-31T10:00:00Z' }

beforeEach(() => {
  vi.mocked(api.listAccounts).mockReset().mockResolvedValue([ADMIN, MINA])
  vi.mocked(api.setCanCreate).mockReset()
})

test('turning creation on saves at once and shows what the server says', async () => {
  vi.mocked(api.setCanCreate).mockResolvedValue({ ...MINA, can_create: true })
  render(<AccountsPanel />)
  const toggle = await screen.findByRole('checkbox', { name: 'mina@example.com can create sessions' })
  expect(toggle).not.toBeChecked()
  await userEvent.click(toggle)
  expect(api.setCanCreate).toHaveBeenCalledWith(2, true)
  await waitFor(() => expect(toggle).toBeChecked())
})

test('the admin can always create, so the toggle is on and fixed', async () => {
  render(<AccountsPanel />)
  const toggle = await screen.findByRole('checkbox', { name: 'boss@example.com can create sessions' })
  expect(toggle).toBeChecked()
  expect(toggle).toBeDisabled()
})

test('a failed change goes back and says why', async () => {
  vi.mocked(api.setCanCreate).mockRejectedValue(new Error('offline'))
  render(<AccountsPanel />)
  const toggle = await screen.findByRole('checkbox', { name: 'mina@example.com can create sessions' })
  await userEvent.click(toggle)
  expect(await screen.findByRole('alert')).toHaveTextContent('offline')
  expect(toggle).not.toBeChecked()
})

test('a list that will not load says why', async () => {
  vi.mocked(api.listAccounts).mockRejectedValue(new Error('offline'))
  render(<AccountsPanel />)
  expect(await screen.findByRole('alert')).toHaveTextContent('offline')
})
