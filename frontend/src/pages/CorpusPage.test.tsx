import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { CorpusEntry } from '../types'
import { CorpusPage } from './CorpusPage'

vi.mock('../api', () => ({ api: { corpus: vi.fn() } }))

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
  ...over,
})

const corpus = [
  entry({ id: 1, phrase: 'Be my guest', korean: '그러세요', examples: ['"Can I use your charger?" "Be my guest."'], source: 'https://www.youtube.com/post/Ugkx1' }),
  entry({ id: 2, phrase: 'touch base', meaning: 'to contact someone briefly', korean: '잠깐 연락하다', setting: 'workplace', sessions: [7] }),
  entry({ id: 3, phrase: 'Bold plan.', korean: '야심 찬 계획이네', source: 'https://www.instagram.com/p/DQ1/' }),
]

beforeEach(() => {
  vi.mocked(api.corpus).mockResolvedValue(corpus)
})

function renderPage() {
  render(
    <MemoryRouter>
      <CorpusPage />
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

it('filters by setting, source and whether a session taught it', async () => {
  renderPage()
  await screen.findByText('Be my guest')
  fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'instagram' } })
  expect(shown()).toEqual(['Bold plan.'])
  fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'all' } })
  fireEvent.change(screen.getByLabelText('Setting'), { target: { value: 'workplace' } })
  expect(shown()).toEqual(['touch base'])
  fireEvent.change(screen.getByLabelText('Setting'), { target: { value: 'all' } })
  fireEvent.change(screen.getByLabelText('Taught'), { target: { value: 'new' } })
  expect(shown()).toEqual(['Be my guest', 'Bold plan.'])
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
