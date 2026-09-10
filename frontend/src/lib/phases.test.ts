import { describe, expect, it } from 'vitest'
import { PHASES, SESSION_SECONDS, formatClock, phaseIndexAt } from './phases'

describe('phaseIndexAt', () => {
  it('starts in the first phase', () => {
    expect(phaseIndexAt(0)).toBe(0)
  })
  it('moves to the next phase after 10 minutes', () => {
    expect(phaseIndexAt(10 * 60 - 1)).toBe(0)
    expect(phaseIndexAt(10 * 60)).toBe(1)
    expect(phaseIndexAt(20 * 60)).toBe(2)
  })
  it('stays in the last phase after the session ends', () => {
    expect(phaseIndexAt(SESSION_SECONDS + 500)).toBe(PHASES.length - 1)
  })
})

describe('formatClock', () => {
  it('renders mm:ss with zero padding', () => {
    expect(formatClock(65)).toBe('01:05')
    expect(formatClock(0)).toBe('00:00')
  })
  it('clamps negative values to zero', () => {
    expect(formatClock(-3)).toBe('00:00')
  })
})
