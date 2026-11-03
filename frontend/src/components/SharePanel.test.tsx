import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { ApiError, api } from '../api'
import { FakeEventSource } from '../test/fakeEventSource'
import { SharePanel } from './SharePanel'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { listShares: vi.fn(), addShare: vi.fn(), removeShare: vi.fn(), findPeople: vi.fn() },
}))

const MINA = { user_id: 2, username: 'mina' }
const JO = { user_id: 3, username: 'jo_kim' }

beforeEach(() => {
  FakeEventSource.instances = []
  vi.mocked(api.listShares).mockReset().mockResolvedValue([MINA])
  vi.mocked(api.addShare).mockReset()
  vi.mocked(api.removeShare).mockReset().mockResolvedValue(undefined)
  vi.mocked(api.findPeople).mockReset().mockResolvedValue([])
})

test('a few letters find someone, and picking them shares and clears the box', async () => {
  vi.mocked(api.findPeople).mockResolvedValue([{ id: 3, username: 'jo_kim' }])
  vi.mocked(api.addShare).mockResolvedValue([JO, MINA])
  render(<SharePanel sessionId={7} />)
  expect(await screen.findByText('mina')).toBeInTheDocument()
  const box = screen.getByRole('combobox', { name: 'Share with' })
  await userEvent.type(box, 'jo')
  await userEvent.click(await screen.findByRole('option', { name: 'jo_kim' }))
  expect(api.findPeople).toHaveBeenLastCalledWith('jo')
  expect(api.addShare).toHaveBeenCalledWith(7, 3)
  expect(await screen.findByText('jo_kim')).toBeInTheDocument()
  await waitFor(() => expect(box).toHaveValue(''))
})

test('the keyboard picks a name too', async () => {
  vi.mocked(api.findPeople).mockResolvedValue([{ id: 3, username: 'jo_kim' }])
  vi.mocked(api.addShare).mockResolvedValue([JO, MINA])
  render(<SharePanel sessionId={7} />)
  await userEvent.type(await screen.findByRole('combobox', { name: 'Share with' }), '김')
  await screen.findByRole('option', { name: 'jo_kim' })
  await userEvent.keyboard('{ArrowDown}{Enter}')
  expect(api.addShare).toHaveBeenCalledWith(7, 3)
})

test('someone it is already shared with is not offered again', async () => {
  vi.mocked(api.findPeople).mockResolvedValue([
    { id: 2, username: 'mina' },
    { id: 4, username: 'minsu' },
  ])
  render(<SharePanel sessionId={7} />)
  await userEvent.type(await screen.findByRole('combobox', { name: 'Share with' }), 'min')
  expect(await screen.findByRole('option', { name: 'minsu' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'mina' })).not.toBeInTheDocument()
})

test('a name nobody has says so', async () => {
  render(<SharePanel sessionId={7} />)
  await userEvent.type(await screen.findByRole('combobox', { name: 'Share with' }), 'zzz')
  expect(await screen.findByText('No one goes by a name like that.')).toBeInTheDocument()
  expect(api.addShare).not.toHaveBeenCalled()
})

test('a share can be ended', async () => {
  render(<SharePanel sessionId={7} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Stop sharing with mina' }))
  expect(api.removeShare).toHaveBeenCalledWith(7, 2)
  await waitFor(() => expect(screen.queryByText('mina')).not.toBeInTheDocument())
})

test('a name cut short on its line still shows in full on hover', async () => {
  render(<SharePanel sessionId={7} />)
  expect(await screen.findByText('mina')).toHaveAttribute('title', 'mina')
})

test('whoever leaves or is added from another tab shows without a reload', async () => {
  render(<SharePanel sessionId={7} />)
  expect(await screen.findByText('mina')).toBeInTheDocument()
  expect(FakeEventSource.open[0].url).toBe('/api/sessions/7/events')

  vi.mocked(api.listShares).mockResolvedValue([JO])
  act(() => FakeEventSource.open[0].send('shares'))
  expect(await screen.findByText('jo_kim')).toBeInTheDocument()
  expect(screen.queryByText('mina')).not.toBeInTheDocument()
})

test('a failed read says so and the next good one clears it', async () => {
  vi.mocked(api.listShares).mockRejectedValue(new Error('offline'))
  render(<SharePanel sessionId={7} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('offline')

  vi.mocked(api.listShares).mockResolvedValue([MINA])
  act(() => FakeEventSource.open[0].send('shares'))
  expect(await screen.findByText('mina')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('a refused share says why and stays on screen through a read that goes well', async () => {
  vi.mocked(api.findPeople).mockResolvedValue([{ id: 9, username: 'gone' }])
  vi.mocked(api.addShare).mockRejectedValue(new ApiError(404, 'That account is not here any more.'))
  render(<SharePanel sessionId={7} />)
  await userEvent.type(await screen.findByRole('combobox', { name: 'Share with' }), 'go')
  await userEvent.click(await screen.findByRole('option', { name: 'gone' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('That account is not here any more.')

  act(() => FakeEventSource.open[0].send('shares'))
  await waitFor(() => expect(api.listShares).toHaveBeenCalledTimes(2))
  expect(screen.getByRole('alert')).toHaveTextContent('That account is not here any more.')
})

test('a search that fails says so instead of looking forever', async () => {
  vi.mocked(api.findPeople).mockRejectedValue(new Error('offline'))
  render(<SharePanel sessionId={7} />)
  await userEvent.type(await screen.findByRole('combobox', { name: 'Share with' }), 'jo')
  expect(await screen.findByText('The search did not go through. Type again to retry.')).toBeInTheDocument()
})

test('the names found stay listed while the next letter is looked up', async () => {
  let answer: (people: { id: number; username: string }[]) => void = () => undefined
  vi.mocked(api.findPeople)
    .mockResolvedValueOnce([{ id: 3, username: 'jo_kim' }])
    .mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
  render(<SharePanel sessionId={7} />)
  const box = await screen.findByRole('combobox', { name: 'Share with' })
  await userEvent.type(box, 'j')
  await screen.findByRole('option', { name: 'jo_kim' })
  await userEvent.type(box, 'o')
  await waitFor(() => expect(api.findPeople).toHaveBeenLastCalledWith('jo'))
  expect(screen.getByRole('option', { name: 'jo_kim' })).toBeInTheDocument()
  act(() => answer([]))
  expect(await screen.findByText('No one goes by a name like that.')).toBeInTheDocument()
})
