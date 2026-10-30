import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionTimer } from './SessionTimer'

describe('SessionTimer', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('counts down from thirty minutes', () => {
    render(<SessionTimer />)
    expect(screen.getByText('30:00')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /start/i }))
    act(() => vi.advanceTimersByTime(65_000))
    expect(screen.getByText('28:55')).toBeInTheDocument()
  })
})
