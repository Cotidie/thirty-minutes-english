import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { useAuth } from '../lib/auth'
import { useCredits } from '../lib/credits'
import type { Me } from '../types'
import { CornerTools } from './CornerTools'

vi.mock('../lib/auth', () => ({ useAuth: vi.fn() }))
vi.mock('../lib/credits', () => ({ useCredits: vi.fn() }))

const USER: Me = { id: 1, email: 'a@example.com', username: 'mina', is_admin: false }

function open(me: Me, rename = vi.fn().mockResolvedValue(undefined)) {
  const logOut = vi.fn().mockResolvedValue(undefined)
  vi.mocked(useCredits).mockReturnValue({ balance: me.is_admin ? null : 12, prices: {}, recent: [], cost: () => 0, canAfford: () => true })
  vi.mocked(useAuth).mockReturnValue({ me, loading: false, logIn: vi.fn(), signUp: vi.fn(), rename, replaceMe: vi.fn(), logOut })
  render(
    <MemoryRouter>
      <CornerTools />
    </MemoryRouter>,
  )
  return logOut
}

it('gives the admin the database, the settings, and a way out', () => {
  open({ ...USER, is_admin: true })
  expect(screen.getByRole('link', { name: 'Database' })).toHaveAttribute('href', '/database')
  expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Credits' })).not.toBeInTheDocument()
})

it('gives everyone else their credits and a way out', async () => {
  const logOut = open(USER)
  expect(screen.getByRole('button', { name: 'Credits' })).toHaveTextContent('12')
  expect(screen.queryByRole('link', { name: 'Database' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Settings' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
  expect(logOut).toHaveBeenCalled()
})

it('shows my username to everyone, the admin too', () => {
  open({ ...USER, is_admin: true })
  expect(screen.getByRole('button', { name: 'Username mina' })).toHaveTextContent('mina')
})

it('changes my username from the corner', async () => {
  const rename = vi.fn().mockResolvedValue(undefined)
  open(USER, rename)
  await userEvent.click(screen.getByRole('button', { name: 'Username mina' }))
  const box = screen.getByRole('textbox', { name: 'Others know you as' })
  expect(box).toHaveValue('mina')
  await userEvent.clear(box)
  await userEvent.type(box, ' 미나 ')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(rename).toHaveBeenCalledWith('미나')
  expect(screen.queryByRole('dialog', { name: 'Username' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Username mina' })).toHaveFocus()
})

it('a username that breaks the rule is not sent, and a refused one says why and stays open', async () => {
  const rename = vi.fn().mockRejectedValue(new ApiError(409, 'Someone already goes by that name.'))
  open(USER, rename)
  await userEvent.click(screen.getByRole('button', { name: 'Username mina' }))
  const box = screen.getByRole('textbox', { name: 'Others know you as' })
  await userEvent.clear(box)
  await userEvent.type(box, 'a b')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(rename).not.toHaveBeenCalled()
  expect(screen.getByText(/2 to 20 letters/)).toHaveClass('is-bad')
  await userEvent.clear(box)
  await userEvent.type(box, 'jo')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Someone already goes by that name.')
  expect(screen.getByRole('dialog', { name: 'Username' })).toBeInTheDocument()
})

it('Escape closes the username box', async () => {
  open(USER)
  await userEvent.click(screen.getByRole('button', { name: 'Username mina' }))
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog', { name: 'Username' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Username mina' })).toHaveFocus()
})
