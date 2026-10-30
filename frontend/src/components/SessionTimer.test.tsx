import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PresenceProvider } from '../lib/presence/PresenceProvider'
import { renderInRoom, WELCOME } from '../test/presenceRoom'
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

  it('falls behind nothing when a hidden tab slows its interval', () => {
    render(<SessionTimer />)
    fireEvent.click(screen.getByRole('button', { name: /start/i }))
    vi.setSystemTime(Date.now() + 600_000)
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText('19:59')).toBeInTheDocument()
  })

  it('pauses, resumes and resets on its own without a session', () => {
    render(<SessionTimer />)
    fireEvent.click(screen.getByRole('button', { name: /start/i }))
    act(() => vi.advanceTimersByTime(5000))
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.getByText('29:55')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.getByText('29:50')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByText('30:00')).toBeInTheDocument()
  })

  it('runs from what arrives, counting on by itself', () => {
    const { socket } = renderInRoom(<SessionTimer />)
    act(() => socket.receive({ type: 'timer', running: true, elapsed: 65, by: 'someone', seq: 1 }))
    expect(screen.getByText('28:55')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText('28:54')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
  })

  it('shows the same time to someone who comes late', () => {
    renderInRoom(<SessionTimer />, { ...WELCOME, timer: { running: true, elapsed: 600 } })
    expect(screen.getByText('20:00')).toBeInTheDocument()
  })

  it('sends start, pause and reset', () => {
    const { socket } = renderInRoom(<SessionTimer />)
    const lastSent = () => socket.sent[socket.sent.length - 1]
    fireEvent.click(screen.getByRole('button', { name: /start/i }))
    expect(lastSent()).toMatchObject({ type: 'timer', running: true, elapsed: 0 })
    act(() => vi.advanceTimersByTime(5000))
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    expect(lastSent()).toMatchObject({ type: 'timer', running: false, elapsed: 5 })
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(lastSent()).toMatchObject({ type: 'timer', running: false, elapsed: 0 })
  })

  it('stops at thirty minutes whatever arrives', () => {
    const { socket } = renderInRoom(<SessionTimer />)
    act(() => socket.receive({ type: 'timer', running: true, elapsed: 86400, by: 'someone', seq: 1 }))
    expect(screen.getByText('Time. Well done.')).toBeInTheDocument()
    expect(screen.getByText('00:00')).toBeInTheDocument()
  })

  it('keeps time alone with the socket down', () => {
    render(
      <PresenceProvider sessionId={3}>
        <SessionTimer />
      </PresenceProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: /start/i }))
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText('29:59')).toBeInTheDocument()
  })
})
