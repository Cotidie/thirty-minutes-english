import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import { useCredits } from '../lib/credits'
import type { CreditEntry } from '../types'
import { CreditsPill } from './CreditsPill'

vi.mock('../lib/credits', () => ({ useCredits: vi.fn() }))
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { findPeople: vi.fn(), giftCredits: vi.fn() },
}))

beforeEach(() => {
  vi.mocked(api.findPeople).mockReset().mockResolvedValue([{ id: 3, username: 'minji' }])
  vi.mocked(api.giftCredits).mockReset().mockResolvedValue(undefined)
})

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

test('credits the admin took back read as taken back', async () => {
  has(40, [{ at: '2026-11-01T09:00:00Z', amount: -34, kind: 'grant', detail: null }])
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  const row = within(screen.getByRole('dialog', { name: 'Credits' })).getByRole('listitem')
  expect(row).toHaveTextContent('Taken back by the admin')
  expect(row).toHaveTextContent('−34')
})

test('a session its maker stopped reads as cancelled, at the half it cost', async () => {
  has(100, [{ at: '2026-11-01T09:00:00Z', amount: -100, kind: 'session_cancelled', detail: 'Trams' }])
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  const row = within(screen.getByRole('dialog', { name: 'Credits' })).getByRole('listitem')
  expect(row).toHaveTextContent('Cancelled session')
  expect(row).toHaveTextContent('Trams')
  expect(row).toHaveTextContent('−100')
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

test('gifts read as to and from whom, with nothing after', async () => {
  has(90, [
    { at: '2026-11-05T09:00:00Z', amount: -200, kind: 'gift_sent', detail: 'minji' },
    { at: '2026-11-04T09:00:00Z', amount: 50, kind: 'gift_received', detail: 'jun' },
  ])
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  const rows = within(screen.getByRole('dialog', { name: 'Credits' })).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('Gift to minji')
  expect(rows[0]).toHaveTextContent('−200')
  expect(rows[1]).toHaveTextContent('Gift from jun')
  expect(rows[1]).toHaveTextContent('+50')
  expect(rows[0].querySelector('.credit-detail')).toBeNull()
  expect(rows[1].querySelector('.credit-detail')).toBeNull()
})

test('the gift button opens the gift screen and Back returns to the charges', async () => {
  has(240)
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gift credits' }))
  expect(screen.getByRole('textbox', { name: 'Gift credits to' })).toBeInTheDocument()
  expect(screen.queryByText('No charges yet.')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(screen.getByText('No charges yet.')).toBeInTheDocument()
})

test('with nothing to give the gift button cannot be pressed', async () => {
  has(0)
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  expect(screen.getByRole('button', { name: 'Gift credits' })).toBeDisabled()
})

test('the panel stays open while a gift is on its way', async () => {
  let land = () => {}
  vi.mocked(api.giftCredits).mockReturnValue(new Promise<void>((resolve) => (land = resolve)))
  has(240)
  render(
    <>
      <p>elsewhere</p>
      <CreditsPill />
    </>,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gift credits' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), '200')
  await userEvent.click(screen.getByRole('button', { name: 'Gift 200 credits' }))
  await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Gift' }))
  await userEvent.keyboard('{Escape}')
  await userEvent.click(screen.getByText('elsewhere'))
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  expect(screen.getByRole('dialog', { name: 'Credits' })).toBeInTheDocument()
  land()
  await waitFor(() => expect(screen.getByRole('dialog', { name: 'Credits' })).toHaveTextContent('Ask the admin for more.'))
})
