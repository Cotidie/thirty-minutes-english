import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import { SpeakButton } from './SpeakButton'

vi.mock('../api', () => ({ api: { speak: vi.fn() } }))

beforeEach(() => {
  vi.mocked(api.speak).mockReset()
})

test('a sentence that cannot be read says why in words, where a phone can see it', async () => {
  vi.mocked(api.speak).mockRejectedValue(new Error('Not enough credits: this needs 1 and you have 0.'))
  render(<SpeakButton text="It was flawed." />)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Read the sentence aloud' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not read it: Not enough credits: this needs 1 and you have 0.')
})

test('trying again takes the words away while it asks', async () => {
  vi.mocked(api.speak).mockRejectedValueOnce(new Error('offline'))
  render(<SpeakButton text="It was said once." />)
  const button = screen.getByRole('button', { name: 'Read the sentence aloud' })
  await userEvent.click(button)
  await screen.findByRole('alert')
  vi.mocked(api.speak).mockReturnValue(new Promise(() => undefined))
  await userEvent.click(button)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
