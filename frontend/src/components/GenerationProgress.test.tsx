import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { percentFor, type JobStatus } from '../lib/progress'
import { GenerationProgress } from './GenerationProgress'

const base: JobStatus = {
  id: 'j',
  topic: 'The Silk Road',
  status: 'running',
  stage: 'searching',
  searches: 2,
  elapsed_seconds: 42,
  stage_elapsed_seconds: 5,
  expected_seconds: 150,
  session_id: null,
  error: null,
}

describe('GenerationProgress', () => {
  it('shows the stage, the clock, and a progress bar', () => {
    render(<GenerationProgress job={base} />)
    expect(screen.getByText('Searching the web (2)')).toBeInTheDocument()
    expect(screen.getByText('00:42 / about 02:30')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', String(percentFor(base)))
  })

  it('keeps the bar from moving backwards across updates', () => {
    const { rerender } = render(<GenerationProgress job={{ ...base, stage: 'writing' }} />)
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(45)
    rerender(<GenerationProgress job={{ ...base, stage: 'starting', searches: 0 }} />)
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(45)
  })
})
