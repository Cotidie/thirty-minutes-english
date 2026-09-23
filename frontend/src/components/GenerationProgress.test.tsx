import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { percentFor, type JobStatus } from '../lib/progress'
import { GenerationProgress } from './GenerationProgress'

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
}

describe('GenerationProgress', () => {
  it('shows the activity, the clock, the counts, and a progress bar', () => {
    render(<GenerationProgress job={base} onCancel={() => undefined} />)
    expect(screen.getByText('Searching "silk road trade"')).toBeInTheDocument()
    expect(screen.getByText('00:42 / about 02:30')).toBeInTheDocument()
    expect(screen.getByText('12.3k in · 850 out · 2 searches')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', String(percentFor(base)))
  })

  it('keeps the bar from moving backwards across updates', () => {
    const { rerender } = render(<GenerationProgress job={{ ...base, stage: 'writing' }} onCancel={() => undefined} />)
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(45)
    rerender(<GenerationProgress job={{ ...base, stage: 'starting', searches: 0 }} onCancel={() => undefined} />)
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(45)
  })

  it('cancels on request', () => {
    const onCancel = vi.fn()
    render(<GenerationProgress job={base} onCancel={onCancel} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
