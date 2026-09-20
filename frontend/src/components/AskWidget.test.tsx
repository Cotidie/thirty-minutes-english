import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { LiveConnection, LiveOptions } from '../lib/liveClient'
import type { LiveEvent } from '../lib/liveSession'
import { AskWidget } from './AskWidget'

const connection = { microphone: {} as MediaStream, say: vi.fn(), correct: vi.fn(), close: vi.fn(), dispose: vi.fn() }
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

/** Fills in the round that a retry just reopened: no button to click. */
async function askAndAnswerAgain() {
  act(() => emit({ type: 'session.started', session: { id: 'live_2' } }))
  act(() => emit({ type: 'session.input_transcript.delta', delta: '눈치 좀 챙겨' }))
  act(() => emit({ type: 'session.output_transcript.delta', delta: 'Read the room.' }))
  act(() => emit({ type: 'session.usage.updated', usage: { seconds: 12 } }))
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

/** Ends the live round: the panel stays up with the transcript and a Save button. */
async function endRound() {
  await userEvent.click(screen.getByRole('button', { name: 'Done' }))
  act(() => emit({ type: 'session.closed', usage: { seconds: 12 } }))
}

describe('AskWidget', () => {
  it('asks with the session topic and keeps the round against that session once saved', async () => {
    renderAt('/s/3')
    await askAndAnswer()
    expect(connect.mock.calls[0][0]).toBe('Digital twins')

    await endRound()
    expect(connection.close).toHaveBeenCalled()
    expect(vi.mocked(api.addAsk)).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(vi.mocked(api.addAsk)).toHaveBeenCalledWith({
      session_id: 3,
      user_text: '눈치 좀 챙겨',
      coach_text: 'Read the room.',
      seconds: 12,
    })
    expect(screen.getByRole('status')).toHaveTextContent('Saved')
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('works off a session, with no topic and no session id', async () => {
    renderAt('/')
    await askAndAnswer()
    expect(connect.mock.calls[0][0]).toBeNull()
    expect(vi.mocked(api.getSession)).not.toHaveBeenCalled()

    await endRound()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(vi.mocked(api.addAsk).mock.calls[0][0].session_id).toBeNull()
  })

  it('throws the round away when the user discards it', async () => {
    renderAt('/')
    await askAndAnswer()
    await endRound()

    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(vi.mocked(api.addAsk)).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Ask/ })).toBeInTheDocument()
  })

  it('retries a round the user talked over, dropping what was said', async () => {
    renderAt('/')
    await askAndAnswer()

    await userEvent.click(screen.getByRole('button', { name: /Retry/ }))
    expect(connection.dispose).toHaveBeenCalled()
    expect(connect).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('눈치 좀 챙겨')).not.toBeInTheDocument()
    expect(vi.mocked(api.addAsk)).not.toHaveBeenCalled()
  })

  it('retries on R and saves on Enter once the round is over', async () => {
    renderAt('/')
    await askAndAnswer()
    await userEvent.keyboard('r')
    expect(connect).toHaveBeenCalledTimes(2)

    await askAndAnswerAgain()
    await endRound()
    await userEvent.keyboard('{Enter}')
    expect(vi.mocked(api.addAsk)).toHaveBeenCalledTimes(1)
  })

  it('closes the round itself once the coach has been quiet, and still waits to be told to save', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderAt('/')
      await askAndAnswer()
      expect(connection.close).not.toHaveBeenCalled()

      await act(async () => {
        vi.advanceTimersByTime(5000)
      })
      expect(connection.close).toHaveBeenCalledTimes(1)
      expect(vi.mocked(api.addAsk)).not.toHaveBeenCalled()
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

  it('will not let a round with no answer be saved', async () => {
    renderAt('/')
    await userEvent.click(screen.getByRole('button', { name: /Ask/ }))
    act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
    act(() => emit({ type: 'session.input_transcript.delta', delta: 'hello?' }))

    await endRound()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('keeps the Save button when the write fails', async () => {
    vi.mocked(api.addAsk).mockRejectedValueOnce(new Error('database is locked'))
    renderAt('/')
    await askAndAnswer()
    await endRound()

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('shows why it could not start', async () => {
    connect.mockRejectedValueOnce(new Error('phrase is off: set OPENAI_API_KEY on the backend'))
    renderAt('/')
    await userEvent.click(screen.getByRole('button', { name: /Ask/ }))
    expect(await screen.findByText(/set OPENAI_API_KEY/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(screen.getByRole('button', { name: /Ask/ })).toBeInTheDocument()
  })
})
