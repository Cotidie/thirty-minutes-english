import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { LiveConnection, LiveOptions } from '../lib/liveClient'
import type { LiveEvent } from '../lib/liveSession'
import { AskWidget } from './AskWidget'

const connection = { finish: vi.fn(), close: vi.fn(), dispose: vi.fn() }
let emit: (e: LiveEvent) => void = () => undefined
type RoundOptions = Omit<LiveOptions, 'start'>
const connect = vi.fn(async (_topic: string | null, opts: RoundOptions): Promise<LiveConnection> => {
  emit = opts.onEvent
  return connection
})

vi.mock('../lib/liveClient', () => ({
  connectAsk: (topic: string | null, opts: RoundOptions) => connect(topic, opts),
}))
vi.mock('../api', () => ({ api: { addAsk: vi.fn(async () => ({})), getSession: vi.fn() } }))

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AskWidget />
    </MemoryRouter>,
  )
}

async function askAndAnswer() {
  await userEvent.click(screen.getByRole('button', { name: /Ask/ }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
  act(() => emit({ type: 'session.input_transcript.delta', delta: '눈치 좀 챙겨' }))
  act(() => emit({ type: 'session.output_transcript.delta', delta: 'Read the room.' }))
  act(() => emit({ type: 'session.usage.updated', usage: { seconds: 12 } }))
}

beforeEach(() => {
  vi.mocked(api.addAsk).mockClear()
  vi.mocked(api.getSession).mockResolvedValue({
    id: 3,
    created_at: '',
    topic: 'Digital twins',
    content: { topic: 'Digital twins', expressions: [], article: { title: '', body: '', questions: [] }, vocabulary: [] },
  })
  connect.mockClear()
  connection.close.mockClear()
  connection.dispose.mockClear()
})

describe('AskWidget', () => {
  it('asks with the session topic and saves the round against that session', async () => {
    renderAt('/s/3')
    await askAndAnswer()
    expect(connect.mock.calls[0][0]).toBe('Digital twins')

    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(connection.close).toHaveBeenCalled()
    expect(vi.mocked(api.addAsk)).toHaveBeenCalledWith({
      session_id: 3,
      user_text: '눈치 좀 챙겨',
      coach_text: 'Read the room.',
      seconds: 12,
    })
  })

  it('works off a session, with no topic and no session id', async () => {
    renderAt('/')
    await askAndAnswer()
    expect(connect.mock.calls[0][0]).toBeNull()
    expect(vi.mocked(api.getSession)).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(vi.mocked(api.addAsk).mock.calls[0][0].session_id).toBeNull()
  })

  it('closes itself once the coach has been quiet, and saves once', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderAt('/')
      await askAndAnswer()
      expect(connection.close).not.toHaveBeenCalled()

      await act(async () => {
        vi.advanceTimersByTime(5000)
      })
      expect(connection.close).toHaveBeenCalledTimes(1)
      expect(vi.mocked(api.addAsk)).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('opens on the A key but not while typing', async () => {
    renderAt('/')
    const field = document.createElement('input')
    document.body.append(field)
    field.focus()
    await userEvent.keyboard('a')
    expect(connect).not.toHaveBeenCalled()
    field.remove()

    document.body.focus()
    await userEvent.keyboard('a')
    expect(connect).toHaveBeenCalled()
  })

  it('saves nothing when the round produced no answer', async () => {
    renderAt('/')
    await userEvent.click(screen.getByRole('button', { name: /Ask/ }))
    act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
    act(() => emit({ type: 'session.input_transcript.delta', delta: 'hello?' }))

    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(vi.mocked(api.addAsk)).not.toHaveBeenCalled()
  })

  it('shows why it could not start', async () => {
    connect.mockRejectedValueOnce(new Error('phrase is off: set OPENAI_API_KEY on the backend'))
    renderAt('/')
    await userEvent.click(screen.getByRole('button', { name: /Ask/ }))
    expect(await screen.findByText(/set OPENAI_API_KEY/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByRole('button', { name: /Ask/ })).toBeInTheDocument()
  })
})
