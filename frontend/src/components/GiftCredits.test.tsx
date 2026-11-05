import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { ApiError, api } from '../api'
import { giftable } from '../lib/gifts'
import { GiftCredits } from './GiftCredits'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { findPeople: vi.fn(), giftCredits: vi.fn() },
}))

beforeEach(() => {
  vi.mocked(api.findPeople).mockReset().mockResolvedValue([{ id: 3, username: 'minji' }])
  vi.mocked(api.giftCredits).mockReset().mockResolvedValue(undefined)
})

function setup(balance = 240) {
  const onClose = vi.fn()
  const onSending = vi.fn()
  render(<GiftCredits balance={balance} onClose={onClose} onSending={onSending} />)
  return { onClose, onSending }
}

async function askToGift(amount: string) {
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), amount)
  await userEvent.click(screen.getByRole('button', { name: `Gift ${amount} credits` }))
}

test('only a whole number from 1 to the balance can be gifted', () => {
  expect(giftable('200', 240)).toBe(200)
  expect(giftable(' 240 ', 240)).toBe(240)
  expect(giftable('1', 240)).toBe(1)
  for (const text of ['', '0', '-3', '1.5', '1e2', 'abc', '241']) expect(giftable(text, 240)).toBeNull()
})

test('a name found and an amount typed ask once, then the gift goes', async () => {
  const { onClose, onSending } = setup()
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  expect(screen.getByRole('heading', { name: 'Gift to minji' })).toBeInTheDocument()
  expect(screen.getByText('You have 240.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gift credits' })).toBeDisabled()
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), '200')
  await userEvent.click(screen.getByRole('button', { name: 'Gift 200 credits' }))
  const ask = screen.getByRole('alertdialog', { name: 'Gift 200 credits to minji?' })
  expect(ask).toHaveTextContent('You will have 40 left. A gift cannot be taken back.')
  expect(within(ask).getByRole('button', { name: 'Cancel' })).toHaveFocus()
  await userEvent.click(within(ask).getByRole('button', { name: 'Gift' }))
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  expect(api.giftCredits).toHaveBeenCalledTimes(1)
  expect(api.giftCredits).toHaveBeenCalledWith(3, 200)
  expect(onSending.mock.calls).toEqual([[true], [false]])
})

test('one credit reads as one credit', async () => {
  setup()
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), '1')
  await userEvent.click(screen.getByRole('button', { name: 'Gift 1 credit' }))
  expect(screen.getByRole('alertdialog', { name: 'Gift 1 credit to minji?' })).toBeInTheDocument()
})

test('Cancel sends nothing and keeps the amount', async () => {
  setup()
  await askToGift('200')
  await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  expect(api.giftCredits).not.toHaveBeenCalled()
  expect(screen.getByRole('textbox', { name: 'Credits to gift' })).toHaveValue('200')
})

test('a refused gift keeps the question open with the reason', async () => {
  vi.mocked(api.giftCredits).mockRejectedValue(new ApiError(402, 'Not enough credits: this needs 200 and you have 150.'))
  const { onClose, onSending } = setup()
  await askToGift('200')
  const ask = screen.getByRole('alertdialog')
  await userEvent.click(within(ask).getByRole('button', { name: 'Gift' }))
  expect(await within(ask).findByRole('alert')).toHaveTextContent('Not enough credits: this needs 200 and you have 150.')
  expect(within(ask).getByRole('button', { name: 'Cancel' })).toBeEnabled()
  expect(onClose).not.toHaveBeenCalled()
  expect(onSending.mock.calls).toEqual([[true], [false]])
})

test('while the gift is on its way neither button can be pressed', async () => {
  let land = () => {}
  vi.mocked(api.giftCredits).mockReturnValue(new Promise<void>((resolve) => (land = resolve)))
  const { onClose } = setup()
  await askToGift('200')
  const ask = screen.getByRole('alertdialog')
  await userEvent.click(within(ask).getByRole('button', { name: 'Gift' }))
  expect(within(ask).getByRole('button', { name: 'Gift' })).toBeDisabled()
  expect(within(ask).getByRole('button', { name: 'Cancel' })).toBeDisabled()
  land()
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
})

test('while the question is open nothing behind it can be used', async () => {
  let land = () => {}
  vi.mocked(api.giftCredits).mockReturnValue(new Promise<void>((resolve) => (land = resolve)))
  const { onClose } = setup()
  await askToGift('200')
  expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled()
  expect(screen.getByRole('textbox', { name: 'Credits to gift' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Gift 200 credits' })).toBeDisabled()
  await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Gift' }))
  await userEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(onClose).not.toHaveBeenCalled()
  land()
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
})

test('a name nobody has says so', async () => {
  vi.mocked(api.findPeople).mockResolvedValue([])
  setup()
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'zz')
  expect(await screen.findByText('No one goes by a name like that.')).toBeInTheDocument()
})

test('Back leaves without a gift', async () => {
  const { onClose } = setup()
  await userEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(onClose).toHaveBeenCalledTimes(1)
  expect(api.giftCredits).not.toHaveBeenCalled()
})
