import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { useCredits } from '../lib/credits'
import type { CreditEntry } from '../types'
import { CreditsPill } from './CreditsPill'

vi.mock('../lib/credits', () => ({ useCredits: vi.fn() }))

function has(balance: number | null, recent: CreditEntry[] = []) {
  vi.mocked(useCredits).mockReturnValue({ balance, prices: {}, recent, cost: () => 0, canAfford: () => true })
}

test('shows the balance and opens the last charges', async () => {
  has(340, [
    { at: '2026-11-01T09:00:00Z', amount: -200, kind: 'session', detail: 'Blame for the Java Sea ferry disaster' },
    { at: '2026-10-30T09:00:00Z', amount: 500, kind: 'grant', detail: null },
  ])
  render(<CreditsPill />)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  const panel = screen.getByRole('dialog', { name: 'Credits' })
  expect(panel).toHaveTextContent('340')
  const rows = within(panel).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('Nov 1')
  expect(rows[0]).toHaveTextContent('Session')
  expect(rows[0]).toHaveTextContent('Blame for the Java Sea ferry disaster')
  expect(rows[0]).toHaveTextContent('−200')
  expect(rows[1]).toHaveTextContent('Added by the admin')
  expect(rows[1]).toHaveTextContent('+500')
  expect(panel).toHaveTextContent('Ask the admin for more.')
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('a click outside closes it, and one inside does not', async () => {
  has(340)
  render(
    <>
      <p>elsewhere</p>
      <CreditsPill />
    </>,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  await userEvent.click(screen.getByText('No charges yet.'))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  await userEvent.click(screen.getByText('elsewhere'))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('a balance taken below zero is marked as short', () => {
  has(-20)
  render(<CreditsPill />)
  const pill = screen.getByRole('button', { name: 'Credits' })
  expect(pill).toHaveTextContent('-20')
  expect(pill).toHaveClass('is-short')
})

test('with nothing known there is no pill', () => {
  has(null)
  render(<CreditsPill />)
  expect(screen.queryByRole('button', { name: 'Credits' })).not.toBeInTheDocument()
})
