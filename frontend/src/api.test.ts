import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ApiError, api } from './api'
import { goToLogin } from './lib/safeNext'

vi.mock('./lib/safeNext', () => ({ goToLogin: vi.fn() }))

function answer(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })))
}

beforeEach(() => vi.mocked(goToLogin).mockClear())
afterEach(() => vi.unstubAllGlobals())

test('a failed request throws its status and the reason the server gave', async () => {
  answer(404, { detail: 'session not found' })
  const error = await api.getSession(1).catch((e: unknown) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error).toMatchObject({ status: 404, message: 'session not found' })
  expect(goToLogin).not.toHaveBeenCalled()
})

test('a 401 outside the auth routes sends you to log in', async () => {
  answer(401, { detail: 'Log in first.' })
  await expect(api.getSession(1)).rejects.toMatchObject({ status: 401 })
  expect(goToLogin).toHaveBeenCalledOnce()
})

test('a 401 from the auth routes is left to the page', async () => {
  answer(401, { detail: "That email and password don't match." })
  await expect(api.login('a@example.com', 'x')).rejects.toMatchObject({ status: 401 })
  answer(401, { detail: 'Log in first.' })
  await expect(api.me()).rejects.toMatchObject({ status: 401 })
  expect(goToLogin).not.toHaveBeenCalled()
})
