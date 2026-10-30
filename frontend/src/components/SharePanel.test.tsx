import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { ApiError, api } from '../api'
import { SharePanel } from './SharePanel'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { listShares: vi.fn(), addShare: vi.fn(), removeShare: vi.fn() },
}))

const MINA = { user_id: 2, email: 'mina@example.com' }
const JO = { user_id: 3, email: 'jo@example.com' }

beforeEach(() => {
  vi.mocked(api.listShares).mockReset().mockResolvedValue([MINA])
  vi.mocked(api.addShare).mockReset()
  vi.mocked(api.removeShare).mockReset().mockResolvedValue(undefined)
})

test('shows who has it, and sharing adds someone and clears the box', async () => {
  vi.mocked(api.addShare).mockResolvedValue([JO, MINA])
  render(<SharePanel sessionId={7} canAdd />)
  expect(await screen.findByText('mina@example.com')).toBeInTheDocument()
  const box = screen.getByLabelText('Share with')
  await userEvent.type(box, 'jo@example.com')
  await userEvent.click(screen.getByRole('button', { name: 'Share' }))
  expect(api.addShare).toHaveBeenCalledWith(7, 'jo@example.com')
  expect(await screen.findByText('jo@example.com')).toBeInTheDocument()
  expect(box).toHaveValue('')
})

test('an email nobody uses says so and stays in the box', async () => {
  vi.mocked(api.addShare).mockRejectedValue(new ApiError(404, 'No account uses that email.'))
  render(<SharePanel sessionId={7} canAdd />)
  const box = await screen.findByLabelText('Share with')
  await userEvent.type(box, 'nobody@example.com')
  await userEvent.click(screen.getByRole('button', { name: 'Share' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No account uses that email.')
  expect(box).toHaveValue('nobody@example.com')
})

test('a share can be ended', async () => {
  render(<SharePanel sessionId={7} canAdd />)
  await userEvent.click(await screen.findByRole('button', { name: 'Stop sharing with mina@example.com' }))
  expect(api.removeShare).toHaveBeenCalledWith(7, 2)
  await waitFor(() => expect(screen.queryByText('mina@example.com')).not.toBeInTheDocument())
})

test('without creation rights the list stays but nobody can be added', async () => {
  render(<SharePanel sessionId={7} canAdd={false} />)
  expect(await screen.findByText('mina@example.com')).toBeInTheDocument()
  expect(screen.queryByLabelText('Share with')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Stop sharing with mina@example.com' })).toBeInTheDocument()
})
