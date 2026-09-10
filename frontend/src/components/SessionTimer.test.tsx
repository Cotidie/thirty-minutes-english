import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionTimer } from './SessionTimer'

function tick(seconds: number) {
  for (let i = 0; i < seconds; i++) act(() => vi.advanceTimersByTime(1000))
}

describe('SessionTimer', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('reports a phase only when the phase changes, not on every tick', () => {
    const onPhaseChange = vi.fn()
    render(<SessionTimer onPhaseChange={onPhaseChange} />)
    fireEvent.click(screen.getByRole('button', { name: /start/i }))

    tick(5)
    expect(onPhaseChange).toHaveBeenCalledTimes(1)
    expect(onPhaseChange).toHaveBeenLastCalledWith(0)

    tick(10 * 60)
    expect(onPhaseChange).toHaveBeenCalledTimes(2)
    expect(onPhaseChange).toHaveBeenLastCalledWith(1)
  })

  it('counts down from thirty minutes', () => {
    render(<SessionTimer onPhaseChange={() => {}} />)
    expect(screen.getByText('30:00')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /start/i }))
    act(() => vi.advanceTimersByTime(65_000))
    expect(screen.getByText('28:55')).toBeInTheDocument()
  })
})
