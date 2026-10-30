import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { ApiError, api } from '../api'
import { AuthProvider, RequireAuth, useAuth } from '../lib/auth'
import type { Me } from '../types'
import { LoginPage } from './LoginPage'
import { SignupPage } from './SignupPage'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { me: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() },
}))

const MINA: Me = { id: 1, email: 'mina@example.com', is_admin: false, can_create: false }

function Inside() {
  const { me, logOut } = useAuth()
  return (
    <button type="button" onClick={() => void logOut()}>
      inside as {me?.email}
    </button>
  )
}

function open(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/" element={<RequireAuth><p>home</p></RequireAuth>} />
          <Route path="/s/:id" element={<RequireAuth><Inside /></RequireAuth>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.me).mockReset().mockRejectedValue(new ApiError(401, 'Log in first.'))
  vi.mocked(api.login).mockReset()
  vi.mocked(api.signup).mockReset()
  vi.mocked(api.logout).mockReset().mockResolvedValue(undefined)
})

test('a page behind the login sends you there and back again', async () => {
  vi.mocked(api.login).mockResolvedValue(MINA)
  open('/s/26')
  const email = await screen.findByLabelText('Email')
  await userEvent.type(email, 'mina@example.com')
  await userEvent.type(screen.getByLabelText('Password'), '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(api.login).toHaveBeenCalledWith('mina@example.com', '12345678')
  expect(await screen.findByText('inside as mina@example.com')).toBeInTheDocument()
})

test('a next that leaves the site goes home instead', async () => {
  vi.mocked(api.login).mockResolvedValue(MINA)
  open('/login?next=%2F%2Fevil.example')
  await userEvent.type(await screen.findByLabelText('Email'), 'mina@example.com')
  await userEvent.type(screen.getByLabelText('Password'), '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('home')).toBeInTheDocument()
})

test('someone already logged in skips both pages', async () => {
  vi.mocked(api.me).mockResolvedValue(MINA)
  open('/login')
  expect(await screen.findByText('home')).toBeInTheDocument()
})

test('a refused login shows the reason and stays on the page', async () => {
  vi.mocked(api.login).mockRejectedValue(new ApiError(401, "That email and password don't match. Check them and try again."))
  open('/login')
  await userEvent.type(await screen.findByLabelText('Email'), 'mina@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'wrong-one')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent("That email and password don't match.")
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
})

test('an empty login asks for both without calling the server', async () => {
  open('/login')
  await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter your email and password.')
  expect(api.login).not.toHaveBeenCalled()
})

test('signing in and signing up link to each other', async () => {
  open('/login')
  await userEvent.click(await screen.findByRole('link', { name: 'Create an account' }))
  expect(await screen.findByLabelText('Confirm password')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('link', { name: 'Sign in' }))
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
})

async function fillSignup(email: string, password: string, confirm: string) {
  await userEvent.type(await screen.findByLabelText('Email'), email)
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.type(screen.getByLabelText('Confirm password'), confirm)
}

test('two passwords that differ say so while typing and never reach the server', async () => {
  open('/signup')
  await fillSignup('mina@example.com', '12345678', '1234')
  expect(screen.getByRole('alert')).toHaveTextContent("The two passwords don't match yet.")
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(api.signup).not.toHaveBeenCalled()
})

test('a bad email is asked for again', async () => {
  open('/signup')
  await fillSignup('not-an-email', '12345678', '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(screen.getAllByText('Enter an email address, like you@example.com.').length).toBeGreaterThan(0)
  expect(api.signup).not.toHaveBeenCalled()
})

test('a short password marks the hint', async () => {
  open('/signup')
  await fillSignup('mina@example.com', '1234567', '1234567')
  const hint = screen.getByText('At least 8 characters.')
  expect(hint).not.toHaveClass('is-bad')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(hint).toHaveClass('is-bad')
  expect(api.signup).not.toHaveBeenCalled()
})

test('a good signup logs you in and goes on', async () => {
  vi.mocked(api.signup).mockResolvedValue(MINA)
  open('/signup')
  await fillSignup('mina@example.com', '12345678', '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(api.signup).toHaveBeenCalledWith('mina@example.com', '12345678')
  expect(await screen.findByText('home')).toBeInTheDocument()
})

test('a signup the server refuses shows why', async () => {
  vi.mocked(api.signup).mockRejectedValue(new ApiError(409, 'An account already uses that email.'))
  open('/signup')
  await fillSignup('mina@example.com', '12345678', '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('An account already uses that email.')
})

test('logging out goes back to the login page', async () => {
  vi.mocked(api.me).mockResolvedValue(MINA)
  open('/s/26')
  await userEvent.click(await screen.findByRole('button', { name: /inside as/ }))
  await waitFor(() => expect(api.logout).toHaveBeenCalled())
  expect(await screen.findByLabelText('Email')).toBeInTheDocument()
})

test('logging out with a login already over still goes to the login page', async () => {
  vi.mocked(api.me).mockResolvedValue(MINA)
  vi.mocked(api.logout).mockRejectedValue(new ApiError(401, 'Log in first.'))
  open('/s/26')
  await userEvent.click(await screen.findByRole('button', { name: /inside as/ }))
  expect(await screen.findByLabelText('Email')).toBeInTheDocument()
})

test('a logout that does not reach the server leaves you logged in', async () => {
  vi.mocked(api.me).mockResolvedValue(MINA)
  vi.mocked(api.logout).mockRejectedValue(new ApiError(502, 'offline'))
  open('/s/26')
  await userEvent.click(await screen.findByRole('button', { name: /inside as/ }))
  await waitFor(() => expect(api.logout).toHaveBeenCalled())
  expect(screen.getByRole('button', { name: /inside as/ })).toBeInTheDocument()
})

test('a broken next does not break the login page', async () => {
  open('/login?next=%2F%2F%255B')
  expect(await screen.findByLabelText('Email')).toBeInTheDocument()
})

test('a next that points at the login page does not loop', async () => {
  vi.mocked(api.me).mockResolvedValue(MINA)
  open('/login?next=%2Flogin')
  expect(await screen.findByText('home')).toBeInTheDocument()
})
