import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCredits } from '../lib/credits'
import { percentFor, type JobStatus } from '../lib/progress'
import { creditsOf } from '../test/credits'
import { GenerationProgress } from './GenerationProgress'

vi.mock('../lib/credits', async (original) => ({ ...(await original<typeof import('../lib/credits')>()), useCredits: vi.fn() }))

const PRICES = { session_cancelled: 100 }

beforeEach(() => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(500, PRICES))
})

const base: JobStatus = {
  id: 'j',
  topic: 'The Silk Road',
  status: 'running',
  stage: 'searching',
  searches: 2,
  activity: 'Searching "silk road trade"',
  input_tokens: 12300,
  output_tokens: 850,
  pictures_done: 0,
  pictures_total: 0,
  elapsed_seconds: 42,
  stage_elapsed_seconds: 5,
  stage_expected_seconds: 30,
  expected_seconds: 150,
  session_id: null,
  error: null,
  spent: false,
}

describe('GenerationProgress', () => {
  it('costs nothing to stop before Claude is called', () => {
    render(<GenerationProgress job={base} onClose={() => undefined} onOpen={() => undefined} />)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel).not.toHaveTextContent('100')
    expect(cancel).not.toHaveAttribute('title')
  })

  it('names what stopping costs once Claude is working', () => {
    render(<GenerationProgress job={{ ...base, spent: true }} onClose={() => undefined} onOpen={() => undefined} />)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel).toHaveTextContent('100')
    expect(cancel).toHaveAttribute('title', 'Stops now. 100 credits stay charged.')
  })

  it('says the session goes once it is saved', () => {
    render(<GenerationProgress job={{ ...base, spent: true, stage: 'illustrating', session_id: 21 }} onClose={() => undefined} onOpen={() => undefined} />)
    const cancel = screen.getByRole('button', { name: 'Cancel and delete' })
    expect(cancel).toHaveTextContent('100')
    expect(cancel).toHaveAttribute('title', 'Stops now. The session is deleted and 100 credits stay charged.')
  })

  it('tells the admin, who pays nothing, only that the session goes', () => {
    vi.mocked(useCredits).mockReturnValue(creditsOf(null, PRICES))
    render(<GenerationProgress job={{ ...base, spent: true, stage: 'illustrating', session_id: 21 }} onClose={() => undefined} onOpen={() => undefined} />)
    const cancel = screen.getByRole('button', { name: 'Cancel and delete' })
    expect(cancel).not.toHaveTextContent('100')
    expect(cancel).toHaveAttribute('title', 'Stops now. The session is deleted.')
  })

  it('asks nothing of a failed job, whatever it spent', () => {
    render(<GenerationProgress job={{ ...base, spent: true, status: 'failed', session_id: 21 }} onClose={() => undefined} onOpen={() => undefined} />)
    const close = screen.getByRole('button', { name: 'Close' })
    expect(close).not.toHaveTextContent('100')
    expect(close).not.toHaveAttribute('title')
  })

  it('shows the activity, the clock, the counts, and a progress bar', () => {
    render(<GenerationProgress job={base} onClose={() => undefined} onOpen={() => undefined} />)
    expect(screen.getByText('Searching "silk road trade"')).toBeInTheDocument()
    expect(screen.getByText('00:42 / about 02:30')).toBeInTheDocument()
    expect(screen.getByText('12.3k in · 850 out · 2 searches')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', String(percentFor(base)))
  })

  it('keeps the bar from moving backwards across updates', () => {
    const { rerender } = render(<GenerationProgress job={{ ...base, stage: 'writing' }} onClose={() => undefined} onOpen={() => undefined} />)
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(45)
    rerender(<GenerationProgress job={{ ...base, stage: 'starting', searches: 0 }} onClose={() => undefined} onOpen={() => undefined} />)
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(45)
  })

  it('cancels on request', () => {
    const onCancel = vi.fn()
    render(<GenerationProgress job={base} onClose={onCancel} onOpen={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('offers the session as soon as the job has saved it, while the pictures are still drawn', () => {
    const onOpen = vi.fn()
    const { rerender } = render(<GenerationProgress job={base} onClose={() => undefined} onOpen={onOpen} />)
    expect(screen.queryByRole('button', { name: 'Open session' })).not.toBeInTheDocument()
    rerender(<GenerationProgress job={{ ...base, stage: 'illustrating', session_id: 21 }} onClose={() => undefined} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open session' }))
    expect(onOpen).toHaveBeenCalledWith(21)
  })

  it('keeps a failed run on screen with its error until closed', () => {
    const onCancel = vi.fn()
    const failed: JobStatus = { ...base, status: 'failed', stage: 'writing', activity: '', elapsed_seconds: 300, error: 'claude timed out after 300s' }
    render(<GenerationProgress job={failed} onClose={onCancel} onOpen={() => undefined} />)
    expect(screen.getByText('Failed while writing the article, expressions, and words')).toBeInTheDocument()
    expect(screen.getByText('after 05:00')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('claude timed out after 300s')
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
