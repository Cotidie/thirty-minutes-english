import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import { FakeEventSource } from '../test/fakeEventSource'
import { CreditsProvider, notEnough, useCredits } from './credits'

vi.mock('../api', () => ({ api: { myCredits: vi.fn() } }))

beforeEach(() => {
  FakeEventSource.instances = []
  vi.mocked(api.myCredits).mockReset()
})

test('outside a provider nothing is short, since nothing is known', () => {
  const { result } = renderHook(() => useCredits())
  expect(result.current.balance).toBeNull()
  expect(result.current.canAfford('session')).toBe(true)
  expect(result.current.cost('session')).toBe(0)
})

test('the provider reads the balance and prices, and reads again on a credits event', async () => {
  vi.mocked(api.myCredits).mockResolvedValueOnce({ balance: 30, prices: { redraw: 10, practice_voice: 10, practice_feedback: 10 }, recent: [] })
  const { result } = renderHook(() => useCredits(), { wrapper: CreditsProvider })
  await waitFor(() => expect(result.current.balance).toBe(30))
  expect(result.current.cost('practice_voice', 'practice_feedback')).toBe(20)
  expect(result.current.canAfford('practice_voice', 'practice_feedback')).toBe(true)
  vi.mocked(api.myCredits).mockResolvedValueOnce({ balance: 5, prices: { redraw: 10 }, recent: [] })
  FakeEventSource.instances[0].send('credits')
  await waitFor(() => expect(result.current.balance).toBe(5))
  expect(result.current.canAfford('redraw')).toBe(false)
})

test('a negative balance affords nothing', async () => {
  vi.mocked(api.myCredits).mockResolvedValueOnce({ balance: -20, prices: { speech: 1 }, recent: [] })
  const { result } = renderHook(() => useCredits(), { wrapper: CreditsProvider })
  await waitFor(() => expect(result.current.balance).toBe(-20))
  expect(result.current.canAfford('speech')).toBe(false)
})

test('the admin, who has no balance, is told nothing costs anything', async () => {
  vi.mocked(api.myCredits).mockResolvedValueOnce({ balance: null, prices: { session: 200 }, recent: [] })
  const { result } = renderHook(() => useCredits(), { wrapper: CreditsProvider })
  await waitFor(() => expect(result.current.prices.session).toBe(200))
  expect(result.current.cost('session')).toBe(0)
  expect(result.current.canAfford('session')).toBe(true)
})

test('notEnough says what it needs and what there is', () => {
  expect(notEnough(10, 3)).toBe('Not enough credits: this needs 10 and you have 3.')
})
