import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveEvent } from '../lib/liveSession'
import type { LiveConnection, LiveOptions } from '../lib/liveClient'
import { api } from '../api'
import { ReadAloud } from './ReadAloud'

vi.mock('../api', () => ({ api: { addReading: vi.fn(async () => ({})) } }))

const connection = { microphone: {} as MediaStream, finish: vi.fn(), say: vi.fn(), close: vi.fn(), dispose: vi.fn() }
let emit: (e: LiveEvent) => void = () => undefined
let drop: () => void = () => undefined
type RoundOptions = Omit<LiveOptions, 'start'>
const connect = vi.fn(async (_paragraph: string, opts: RoundOptions): Promise<LiveConnection> => {
  emit = opts.onEvent
  drop = opts.onDisconnect
  return connection
})

vi.mock('../lib/liveClient', () => ({
  connectReadAloud: (paragraph: string, opts: RoundOptions) => connect(paragraph, opts),
}))

function renderIdle(active = false) {
  const onStart = vi.fn()
  const onEnd = vi.fn()
  render(<ReadAloud paragraph="Researchers verified it." sessionId={3} active={active} onStart={onStart} onEnd={onEnd} />)
  return { onStart, onEnd }
}

beforeEach(() => {
  vi.mocked(api.addReading).mockClear()
  connect.mockClear()
  connection.finish.mockClear()
  connection.close.mockClear()
})

describe('ReadAloud', () => {
  it('connects on click, shows captions, and relays Finish and Stop', async () => {
    const { onStart } = renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(onStart).toHaveBeenCalled()
    expect(connect.mock.calls[0][0]).toBe('Researchers verified it.')
    expect(screen.getByRole('status')).toHaveTextContent('Connecting…')

    act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
    expect(screen.getByRole('status')).toHaveTextContent('Listening')

    act(() => {
      emit({ type: 'session.input_transcript.delta', delta: 'Researchers berified' })
      emit({ type: 'session.output_transcript.delta', delta: 'Quick one: verify.' })
      emit({ type: 'session.usage.updated', usage: { seconds: 14 } })
    })
    expect(screen.getByText('Researchers berified')).toBeInTheDocument()
    expect(screen.getByText('Quick one: verify.')).toBeInTheDocument()
    expect(screen.getByText('14s')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Finish' }))
    expect(connection.finish).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(connection.close).toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Wrapping up')
  })

  it('returns to idle after the round closes and reports the end', async () => {
    const { onEnd } = renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    act(() => emit({ type: 'session.started' }))
    act(() => emit({ type: 'session.closed', usage: { seconds: 90 } }))
    expect(screen.getByRole('status')).toHaveTextContent('Round over')
    expect(screen.getByText('90s')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onEnd).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument()
  })

  it('shows the failure when the connection cannot start or drops', async () => {
    connect.mockRejectedValueOnce(new Error('Permission denied'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('Permission denied')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Could not start')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))

    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    act(() => emit({ type: 'session.started' }))
    act(() => drop())
    expect(screen.getByText('Connection dropped before the round ended.')).toBeInTheDocument()
  })

  it('is disabled while another paragraph holds the microphone', () => {
    renderIdle(true)
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled()
  })
})

describe('ReadAloud records', () => {
  it('files a round the coach spoke in, and skips a silent one', async () => {
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
    act(() => emit({ type: 'session.input_transcript.delta', delta: 'researchers berified it' }))
    act(() => emit({ type: 'session.output_transcript.delta', delta: 'Quick one: that was berified.' }))
    act(() => emit({ type: 'session.closed', usage: { seconds: 31 } }))

    expect(vi.mocked(api.addReading)).toHaveBeenCalledWith({
      session_id: 3,
      paragraph: 'Researchers verified it.',
      user_text: 'researchers berified it',
      coach_text: 'Quick one: that was berified.',
      seconds: 31,
    })

    vi.mocked(api.addReading).mockClear()
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    act(() => emit({ type: 'session.started', session: { id: 'live_2' } }))
    act(() => emit({ type: 'session.input_transcript.delta', delta: 'researchers verified it' }))
    act(() => emit({ type: 'session.closed', usage: { seconds: 28 } }))
    expect(vi.mocked(api.addReading)).not.toHaveBeenCalled()
  })
})
