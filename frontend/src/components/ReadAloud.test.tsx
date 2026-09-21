import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveEvent } from '../lib/liveSession'
import type { LiveConnection, LiveOptions } from '../lib/liveClient'
import type { AzureWord } from '../lib/assessor/judge'
import type { AssessorOptions } from '../lib/assessor/azure'
import { api } from '../api'
import { COACH_SILENCE_MS, ReadAloud } from './ReadAloud'

const session = { token: 'eyJ.t', region: 'koreacentral', word_score: 60, break_confidence: 0.75 }
vi.mock('../api', () => ({
  api: {
    addReading: vi.fn(async () => ({})),
    assessorToken: vi.fn(async () => session),
  },
}))

const track = { stop: vi.fn(), enabled: true }
const microphone = { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream
Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: vi.fn(async () => microphone) }, configurable: true })

let segment: (words: AzureWord[], text: string) => void = () => undefined
const assessor = { stop: vi.fn(async () => undefined) }
const startAssessor = vi.fn(async (opts: AssessorOptions) => {
  segment = opts.onSegment
  return assessor
})
vi.mock('../lib/assessor/azure', () => ({ startAzureAssessor: (opts: AssessorOptions) => startAssessor(opts) }))

const coachTrack = { enabled: true }
const connection = {
  microphone: { getAudioTracks: () => [coachTrack] } as unknown as MediaStream,
  say: vi.fn(),
  correct: vi.fn(),
  close: vi.fn(),
  dispose: vi.fn(),
}
let emit: (e: LiveEvent) => void = () => undefined
type RoundOptions = Omit<LiveOptions, 'start'>
const connect = vi.fn(async (_paragraph: string, opts: RoundOptions): Promise<LiveConnection> => {
  emit = opts.onEvent
  return connection
})
vi.mock('../lib/liveClient', () => ({
  connectReadAloud: (paragraph: string, opts: RoundOptions) => connect(paragraph, opts),
}))

const berified: AzureWord = {
  Word: 'verified',
  Offset: 0,
  Duration: 1,
  PronunciationAssessment: { AccuracyScore: 41, ErrorType: 'Mispronunciation' },
  Phonemes: [{ Phoneme: 'v', PronunciationAssessment: { AccuracyScore: 8, NBestPhonemes: [{ Phoneme: 'b', Score: 80 }] } }],
}
const verified: AzureWord = { Word: 'verified', Offset: 0, Duration: 1, PronunciationAssessment: { AccuracyScore: 88, ErrorType: 'None' } }

function renderIdle(active = false) {
  const onStart = vi.fn()
  const onEnd = vi.fn()
  render(<ReadAloud paragraph="Researchers verified it." sessionId={3} active={active} onStart={onStart} onEnd={onEnd} />)
  return { onStart, onEnd }
}

/** Click Read aloud and wait until Azure is listening. */
async function startRound() {
  await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Listening'))
}

beforeEach(() => {
  vi.mocked(api.addReading).mockClear()
  vi.mocked(api.assessorToken).mockClear().mockResolvedValue(session)
  connect.mockClear()
  startAssessor.mockClear()
  assessor.stop.mockClear()
  track.stop.mockClear()
  coachTrack.enabled = true
  for (const fn of [connection.correct, connection.close, connection.dispose]) fn.mockClear()
})

describe('ReadAloud round', () => {
  it('opens the microphone for Azure only, shows what was heard, and files the round on Done', async () => {
    const { onStart } = renderIdle()
    await startRound()
    expect(onStart).toHaveBeenCalled()
    expect(connect).not.toHaveBeenCalled()
    expect(startAssessor.mock.calls[0][0]).toMatchObject({ microphone, paragraph: 'Researchers verified it.', session })

    act(() => segment([berified], 'Researchers berified'))
    act(() => segment([], 'it.'))
    expect(screen.getByText('Researchers berified it.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())
    expect(track.stop).toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Round over')
    await waitFor(() =>
      expect(vi.mocked(api.addReading)).toHaveBeenCalledWith(
        expect.objectContaining({
          session_id: 3,
          paragraph: 'Researchers verified it.',
          user_text: 'Researchers berified it.',
          coach_text: '',
          corrections: [{ kind: 'pronunciation', word: 'verified', heard: 'b for v', fix: 'v', repeated_ok: false }],
        }),
      ),
    )
  })

  it('files nothing for a clean round, and returns to idle on Close', async () => {
    const { onEnd } = renderIdle()
    await startRound()
    act(() => segment([verified], 'Researchers verified it.'))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())
    expect(vi.mocked(api.addReading)).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onEnd).toHaveBeenCalledWith(false)
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /b for v/ })).not.toBeInTheDocument()
  })

  it('keeps the marks after Close, still clickable, with Read again on offer', async () => {
    const { onEnd } = renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onEnd).toHaveBeenCalledWith(true)

    expect(screen.getByRole('button', { name: 'Read again' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalled())
    expect(screen.getByRole('note', { name: 'verified' })).toHaveTextContent("You said /b/. It's /v/.")
  })

  it('fails before touching the microphone when the assessor is off', async () => {
    vi.mocked(api.assessorToken).mockRejectedValueOnce(new Error('Read aloud is off: set AZURE_SPEECH_KEY in Settings'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('Read aloud is off: set AZURE_SPEECH_KEY in Settings')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Could not start')
    expect(startAssessor).not.toHaveBeenCalled()
  })

  it('is disabled while another paragraph holds the microphone', () => {
    renderIdle(true)
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled()
  })
})

describe('ReadAloud marks', () => {
  it('marks a finding on the paragraph and turns it green when the word comes back clean', async () => {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    const hit = screen.getByRole('button', { name: 'verified: b for v' })
    expect(hit).toHaveClass('is-pronunciation')
    expect(connect).not.toHaveBeenCalled()

    act(() => segment([verified], 'verified'))
    expect(hit).toHaveClass('is-ok')
  })

  it('dials the coach for a clicked mark, mutes its microphone, and hangs up once it has been quiet', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderIdle()
      await startRound()
      act(() => segment([berified], 'berified'))

      await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
      await waitFor(() => expect(connect).toHaveBeenCalledWith('Researchers verified it.', expect.anything()))
      expect(coachTrack.enabled).toBe(false)
      const card = screen.getByRole('note', { name: 'verified' })
      expect(card).toHaveTextContent("You said /b/. It's /v/.")
      expect(card).toHaveTextContent('v as in Van: Top teeth on the lower lip, voice on.')

      act(() => emit({ type: 'session.started' }))
      expect(connection.correct).toHaveBeenCalledWith(expect.objectContaining({ word: 'verified', at: 1 }))

      act(() => emit({ type: 'session.output_transcript.delta', delta: 'You said berify. ' }))
      act(() => emit({ type: 'session.output_transcript.delta', delta: "It's verify." }))
      expect(connection.close).not.toHaveBeenCalled()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(COACH_SILENCE_MS)
      })
      expect(connection.close).toHaveBeenCalled()
      act(() => emit({ type: 'session.closed' }))
      expect(connection.dispose).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('sends the correction when session.started arrives during connect', async () => {
    connect.mockImplementationOnce(async (_paragraph, opts) => {
      opts.onEvent({ type: 'session.started' })
      return connection
    })
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connection.correct).toHaveBeenCalledTimes(1))
  })

  it('still dials the coach after Done, and drops the call on Close', async () => {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())

    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(connection.dispose).toHaveBeenCalled()
  })
})
