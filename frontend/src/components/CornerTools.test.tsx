import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { useAuth } from '../lib/auth'
import { useCredits } from '../lib/credits'
import type { Me } from '../types'
import { CornerTools } from './CornerTools'

vi.mock('../lib/auth', () => ({ useAuth: vi.fn() }))
vi.mock('../lib/credits', () => ({ useCredits: vi.fn() }))

const USER: Me = { id: 1, email: 'a@example.com', is_admin: false }

function open(me: Me) {
  const logOut = vi.fn().mockResolvedValue(undefined)
  vi.mocked(useCredits).mockReturnValue({ balance: me.is_admin ? null : 12, prices: {}, recent: [], cost: () => 0, canAfford: () => true })
  vi.mocked(useAuth).mockReturnValue({ me, loading: false, logIn: vi.fn(), signUp: vi.fn(), logOut })
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
