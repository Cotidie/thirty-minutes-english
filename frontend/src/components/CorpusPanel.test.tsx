import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { CorpusEntry } from '../types'
import { CorpusPanel } from './CorpusPanel'

vi.mock('../api', () => ({ api: { corpus: vi.fn(), deleteExpression: vi.fn() } }))

const entry = (over: Partial<CorpusEntry>): CorpusEntry => ({
  id: 1,
  phrase: 'p',
  meaning: 'm',
  synonyms: [],
  usage_note: 'n',
  examples: [],
  korean: null,
  setting: 'casual',
  source: 'https://www.youtube.com/post/Ugkx2',
  added_at: '2026-10-26T00:00:00+00:00',
  sessions: [],
  swapped: [],
  ...over,
})

const corpus = [
  entry({ id: 1, phrase: 'Be my guest', korean: '그러세요', examples: ['"Can I use your charger?" "Be my guest."'], source: 'https://www.youtube.com/post/Ugkx1' }),
  entry({ id: 2, phrase: 'touch base', meaning: 'to contact someone briefly', korean: '잠깐 연락하다', setting: 'workplace', sessions: [7] }),
  entry({ id: 3, phrase: 'Bold plan.', korean: '야심 찬 계획이네', source: 'https://www.instagram.com/p/DQ1/', swapped: [9] }),
]

beforeEach(() => {
  vi.mocked(api.corpus).mockResolvedValue(corpus)
})

function renderPage() {
  render(
    <MemoryRouter>
      <CorpusPanel />
    </MemoryRouter>,
  )
}

function shown() {
  return screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
}

it('lists the whole corpus with its count, its Korean and its examples', async () => {
  renderPage()
  expect(await screen.findByText('Be my guest')).toBeInTheDocument()
  expect(screen.getByText('3 of 3')).toBeInTheDocument()
  expect(screen.getByText('그러세요')).toBeInTheDocument()
  expect(screen.getByText('"Can I use your charger?" "Be my guest."')).toBeInTheDocument()
})

it('searches the phrase, the meaning and the Korean', async () => {
  renderPage()
  await screen.findByText('Be my guest')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '연락' } })
  expect(shown()).toEqual(['touch base'])
  expect(screen.getByText('1 of 3')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'CONTACT' } })
  expect(shown()).toEqual(['touch base'])
})

it('filters by setting, source and whether a session used it', async () => {
  renderPage()
  await screen.findByText('Be my guest')
  fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'instagram' } })
  expect(shown()).toEqual(['Bold plan.'])
  fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'all' } })
  fireEvent.change(screen.getByLabelText('Setting'), { target: { value: 'workplace' } })
  expect(shown()).toEqual(['touch base'])
  fireEvent.change(screen.getByLabelText('Setting'), { target: { value: 'all' } })
  fireEvent.change(screen.getByLabelText('Used'), { target: { value: 'new' } })
  expect(shown()).toEqual(['Be my guest'])
  fireEvent.change(screen.getByLabelText('Used'), { target: { value: 'used' } })
  expect(shown()).toEqual(['touch base', 'Bold plan.'])
})

it('links each entry to its post and to the sessions that taught it', async () => {
  renderPage()
  await screen.findByText('Be my guest')
  expect(screen.getAllByRole('link', { name: 'YouTube post' }).map((a) => a.getAttribute('href'))).toEqual([
    'https://www.youtube.com/post/Ugkx1',
    'https://www.youtube.com/post/Ugkx2',
  ])
  expect(screen.getByRole('link', { name: 'Instagram post' })).toHaveAttribute('href', 'https://www.instagram.com/p/DQ1/')
  expect(screen.getByRole('link', { name: 'Session 7' })).toHaveAttribute('href', '/s/7')
})

it('says so when the corpus does not load', async () => {
  vi.mocked(api.corpus).mockRejectedValue(new Error('500 Internal Server Error'))
  renderPage()
  expect(await screen.findByText(/Could not load the corpus: 500/)).toBeInTheDocument()
})

it('says which session an expression was swapped out of', async () => {
  renderPage()
  await screen.findByText('Be my guest')
  expect(screen.getByText(/Swapped out of/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Session 9' })).toHaveAttribute('href', '/s/9')
})

it('deletes an expression after a confirm that names the sessions it leaves', async () => {
  vi.mocked(api.deleteExpression).mockResolvedValue(undefined)
  renderPage()
  await screen.findByText('Be my guest')
  fireEvent.click(screen.getByRole('button', { name: 'Delete touch base' }))
  expect(screen.getByText('Also takes it out of Session 7.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByText('Also takes it out of Session 7.')).not.toBeInTheDocument()
  expect(api.deleteExpression).not.toHaveBeenCalled()

  fireEvent.click(screen.getByRole('button', { name: 'Delete touch base' }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete for good' }))
  await waitFor(() => expect(shown()).toEqual(['Be my guest', 'Bold plan.']))
  expect(api.deleteExpression).toHaveBeenCalledWith(2)
  expect(screen.getByText('2 of 2')).toBeInTheDocument()
})

it('keeps the expression and says so when the delete fails', async () => {
  vi.mocked(api.deleteExpression).mockRejectedValue(new Error('500 Internal Server Error'))
  renderPage()
  await screen.findByText('Be my guest')
  fireEvent.click(screen.getByRole('button', { name: 'Delete Be my guest' }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete for good' }))
  expect(await screen.findByText(/Could not delete it: 500/)).toBeInTheDocument()
  expect(shown()).toContain('Be my guest')
})

it('draws the first fifty of a long corpus and counts them all', async () => {
  vi.mocked(api.corpus).mockResolvedValue(Array.from({ length: 60 }, (_, i) => entry({ id: i + 1, phrase: `phrase ${i + 1}` })))
  renderPage()
  expect(await screen.findByText('60 of 60')).toBeInTheDocument()
  expect(shown()).toHaveLength(50)
})
