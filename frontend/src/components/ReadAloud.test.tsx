import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveEvent } from '../lib/liveSession'
import type { LiveConnection, LiveOptions } from '../lib/liveClient'
import type { AzureWord } from '../lib/assessor/judge'
import type { AssessorOptions } from '../lib/assessor/azure'
import { api } from '../api'
import { ReadAloud } from './ReadAloud'

const session = { token: 'eyJ.t', region: 'koreacentral', word_score: 60, break_confidence: 0.75 }
vi.mock('../api', () => ({
  api: {
    addReading: vi.fn(async () => ({})),
    assessorToken: vi.fn(async () => session),
  },
}))

let segment: (words: AzureWord[]) => void = () => undefined
const assessor = { stop: vi.fn(async () => undefined) }
const startAssessor = vi.fn(async (opts: AssessorOptions) => {
  segment = opts.onSegment
  return assessor
})
vi.mock('../lib/assessor/azure', () => ({ startAzureAssessor: (opts: AssessorOptions) => startAssessor(opts) }))

const connection = { microphone: {} as MediaStream, finish: vi.fn(), say: vi.fn(), correct: vi.fn(), confirm: vi.fn(), review: vi.fn(), close: vi.fn(), dispose: vi.fn() }
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
  vi.mocked(api.assessorToken).mockClear().mockResolvedValue(session)
  connect.mockClear()
  startAssessor.mockClear()
  assessor.stop.mockClear()
  for (const fn of [connection.finish, connection.close, connection.correct, connection.confirm, connection.review]) fn.mockClear()
})

/** Click Read aloud and wait until both the coach and the assessor are up. */
async function startRound() {
  await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
  await waitFor(() => expect(startAssessor).toHaveBeenCalled())
}

describe('ReadAloud', () => {
  it('connects on click, shows captions, and relays Done and Stop', async () => {
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

    await waitFor(() => expect(startAssessor).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(connection.review).toHaveBeenCalledWith([])
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

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onEnd).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument()
  })

  it('shows the failure when the connection cannot start or drops', async () => {
    connect.mockRejectedValueOnce(new Error('Permission denied'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('Permission denied')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Could not start')
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

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
      corrections: [],
    })

    vi.mocked(api.addReading).mockClear()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    act(() => emit({ type: 'session.started', session: { id: 'live_2' } }))
    act(() => emit({ type: 'session.input_transcript.delta', delta: 'researchers verified it' }))
    act(() => emit({ type: 'session.closed', usage: { seconds: 28 } }))
    expect(vi.mocked(api.addReading)).not.toHaveBeenCalled()
  })
})

const berified: AzureWord = {
  Word: 'verified',
  Offset: 0,
  Duration: 1,
  PronunciationAssessment: { AccuracyScore: 41, ErrorType: 'Mispronunciation' },
  Phonemes: [{ Phoneme: 'v', PronunciationAssessment: { AccuracyScore: 8, NBestPhonemes: [{ Phoneme: 'b', Score: 80 }] } }],
}
const verified: AzureWord = { Word: 'verified', Offset: 0, Duration: 1, PronunciationAssessment: { AccuracyScore: 88, ErrorType: 'None' } }

describe('ReadAloud assessor', () => {
  it('starts Azure on the round microphone with the paragraph, and stops it when the round closes', async () => {
    renderIdle()
    await startRound()
    expect(startAssessor.mock.calls[0][0]).toMatchObject({ microphone: connection.microphone, paragraph: 'Researchers verified it.', session })
    act(() => emit({ type: 'session.started' }))
    act(() => emit({ type: 'session.closed', usage: { seconds: 20 } }))
    expect(assessor.stop).toHaveBeenCalled()
  })

  it('marks a finding on the paragraph without a word from the coach', async () => {
    renderIdle()
    await startRound()
    act(() => emit({ type: 'session.started' }))
    act(() => segment([berified]))
    const hit = screen.getByRole('button', { name: 'verified: b for v' })
    expect(hit).toHaveClass('is-pronunciation')
    expect(connection.correct).not.toHaveBeenCalled()
    expect(screen.queryByText(/say v/)).not.toBeInTheDocument()
  })

  it('opens the card and has the coach speak when a mark is clicked, once per word', async () => {
    renderIdle()
    await startRound()
    act(() => emit({ type: 'session.started' }))
    act(() => segment([berified]))

    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    expect(connection.correct).toHaveBeenCalledWith(expect.objectContaining({ kind: 'pronunciation', word: 'verified', heard: 'b for v', at: 1 }))
    expect(screen.getByText(/heard b for v: say v/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    expect(connection.correct).toHaveBeenCalledTimes(1)
  })

  it('confirms a clicked finding when the word comes back clean, and saves it as repeated', async () => {
    renderIdle()
    await startRound()
    act(() => emit({ type: 'session.started' }))
    act(() => segment([berified]))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))

    act(() => segment([verified]))
    expect(connection.confirm).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'verified: b for v' })).toHaveClass('is-ok')

    act(() => emit({ type: 'session.closed', usage: { seconds: 40 } }))
    expect(vi.mocked(api.addReading)).toHaveBeenCalledWith(
      expect.objectContaining({
        corrections: [{ kind: 'pronunciation', word: 'verified', heard: 'b for v', fix: 'v', repeated_ok: true }],
      }),
    )
  })

  it('stays silent when an unclicked finding clears itself', async () => {
    renderIdle()
    await startRound()
    act(() => emit({ type: 'session.started' }))
    act(() => segment([berified]))
    act(() => segment([verified]))
    expect(connection.confirm).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'verified: b for v' })).toHaveClass('is-ok')
  })

  it('reviews what is still open on Done', async () => {
    renderIdle()
    await startRound()
    act(() => emit({ type: 'session.started' }))
    act(() => segment([berified]))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(connection.review).toHaveBeenCalledWith([expect.objectContaining({ word: 'verified' })])
  })

  it('fails the round before connecting when the assessor is off', async () => {
    vi.mocked(api.assessorToken).mockRejectedValueOnce(new Error('Read aloud is off: set AZURE_SPEECH_KEY in Settings'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('Read aloud is off: set AZURE_SPEECH_KEY in Settings')).toBeInTheDocument()
    expect(connect).not.toHaveBeenCalled()
  })
})
