import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import { DatabasePage } from './DatabasePage'

vi.mock('../api', () => ({ api: { corpus: vi.fn(), topicLibrary: vi.fn() } }))

beforeEach(() => {
  vi.mocked(api.corpus).mockResolvedValue([])
  vi.mocked(api.topicLibrary).mockResolvedValue({ topics: [], labels: {} })
})

function renderAt(path: string, tab: 'expressions' | 'topics') {
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
  expect(api.topicLibrary).not.toHaveBeenCalled()
})

it('shows the topics on their tab', async () => {
  renderAt('/database/topics', 'topics')
  expect(await screen.findByText('0 of 0')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Topics' })).toHaveAttribute('aria-current', 'page')
  expect(api.corpus).not.toHaveBeenCalled()
})
