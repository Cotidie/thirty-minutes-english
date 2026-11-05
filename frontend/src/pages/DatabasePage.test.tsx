import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import { DatabasePage } from './DatabasePage'

vi.mock('../api', () => ({
  api: { corpus: vi.fn(), topicLibrary: vi.fn(), listJobs: vi.fn(), listAccounts: vi.fn(), accountCredits: vi.fn() },
}))

const MINA = { id: 2, email: 'mina@example.com', username: '미나', is_admin: false, created_at: '2026-10-31T10:00:00Z', credits: 340 }

beforeEach(() => {
  vi.mocked(api.corpus).mockResolvedValue([])
  vi.mocked(api.topicLibrary).mockResolvedValue({ topics: [], labels: {} })
  vi.mocked(api.listJobs).mockResolvedValue([])
  vi.mocked(api.listAccounts).mockResolvedValue([MINA])
  vi.mocked(api.accountCredits).mockResolvedValue([])
})

function renderAt(path: string, tab: 'expressions' | 'topics' | 'accounts') {
  render(
    <MemoryRouter initialEntries={[path]}>
      <DatabasePage tab={tab} />
    </MemoryRouter>,
  )
}

it('opens on the expressions, with a tab for the topics', async () => {
  renderAt('/database', 'expressions')
  expect(await screen.findByText('0 of 0')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Expressions' })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: 'Topics' })).toHaveAttribute('href', '/database/topics')
  expect(screen.getByRole('link', { name: 'Accounts' })).toHaveAttribute('href', '/database/accounts')
  expect(api.topicLibrary).not.toHaveBeenCalled()
  expect(api.listAccounts).not.toHaveBeenCalled()
})

it('shows the topics on their tab', async () => {
  renderAt('/database/topics', 'topics')
  expect(await screen.findByText('0 of 0')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Topics' })).toHaveAttribute('aria-current', 'page')
  expect(api.corpus).not.toHaveBeenCalled()
})

it('shows the accounts on their tab', async () => {
  renderAt('/database/accounts', 'accounts')
  expect(await screen.findByText('mina@example.com')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Accounts' })).toHaveAttribute('aria-current', 'page')
  expect(api.corpus).not.toHaveBeenCalled()
  expect(api.topicLibrary).not.toHaveBeenCalled()
})
