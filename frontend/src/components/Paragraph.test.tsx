import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { Shown } from '../lib/assessor/judge'
import { useCredits } from '../lib/credits'
import { pairSentences } from '../lib/sentences'
import { creditsOf } from '../test/credits'
import { Paragraph } from './Paragraph'

vi.mock('../api', () => ({ api: { addReading: vi.fn(), assessorToken: vi.fn() } }))
vi.mock('../lib/liveClient', () => ({ connectReadAloud: vi.fn(), connectSummary: vi.fn() }))
vi.mock('../lib/assessor/azure', () => ({ startAzureAssessor: vi.fn() }))
vi.mock('../lib/credits', async (original) => ({ ...(await original<typeof import('../lib/credits')>()), useCredits: vi.fn() }))

const TEXT = 'It was not flawed at all.'
const FLAWED: Shown = { word: 'flawed', heard: 'flowed', fix: 'flɔːd', at: 3, score: 40, sounds: [], repeated_ok: false }

function renderMarked() {
  render(
    <Paragraph
      paragraph={{ id: 1, text: TEXT }}
      pieces={pairSentences([TEXT], [{ en: TEXT, ko: '전혀 결함이 없었다.' }])[0]}
      spans={[]}
      summaries={[]}
      saved={[FLAWED]}
      onSummary={vi.fn()}
      active={false}
      onStart={vi.fn()}
      onEnd={vi.fn()}
    />,
  )
}

const PRICES = { read_aloud_token: 5, read_aloud_voice: 5, summary_voice: 10, summary_feedback: 10 }

beforeEach(() => {
  vi.mocked(useCredits).mockReset()
})

test('short of credits, a mark, Read again and Summarize are off and say why', () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(2, PRICES))
  renderMarked()
  const mark = screen.getByRole('button', { name: 'flawed: flowed' })
  expect(mark).toBeDisabled()
  expect(mark).toHaveAttribute('title', 'Not enough credits: this needs 5 and you have 2.')
  const read = screen.getByRole('button', { name: 'Read again' })
  expect(read).toBeDisabled()
  expect(read).toHaveAttribute('title', 'Not enough credits: this needs 5 and you have 2.')
  const summarize = screen.getByRole('button', { name: 'Summarize' })
  expect(summarize).toBeDisabled()
  expect(summarize).toHaveAttribute('title', 'Not enough credits: this needs 20 and you have 2.')
})

test('with 5 left, a mark and Read again still work and Summarize, which takes 20, does not', () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(5, PRICES))
  renderMarked()
  expect(screen.getByRole('button', { name: 'flawed: flowed' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Read again' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Summarize' })).toBeDisabled()
})

test('with enough credits each button shows its price and a mark names what hearing the coach costs', () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(50, PRICES))
  renderMarked()
  expect(screen.getByRole('button', { name: 'flawed: flowed' })).toHaveAttribute('title', 'flawed: flowed · Hear the coach · 5')
  expect(screen.getByRole('button', { name: 'Read again' })).toHaveTextContent('5')
  expect(screen.getByRole('button', { name: 'Summarize' })).toHaveTextContent('20')
})

test('the admin, who is charged nothing, sees no price', () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(null, PRICES))
  renderMarked()
  expect(screen.getByRole('button', { name: 'flawed: flowed' })).toHaveAttribute('title', 'flawed: flowed')
  expect(screen.getByRole('button', { name: 'Read again' })).toHaveTextContent(/^Read again$/)
  expect(screen.getByRole('button', { name: 'Summarize' })).toHaveTextContent(/^Summarize$/)
})
