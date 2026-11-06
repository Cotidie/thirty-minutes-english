import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveEvent } from '../lib/liveSession'
import type { LiveConnection, LiveOptions } from '../lib/liveClient'
import type { AzureWord, Shown } from '../lib/assessor/judge'
import type { AssessorOptions } from '../lib/assessor/azure'
import { api } from '../api'
import { pairSentences } from '../lib/sentences'
import { PresenceProvider } from '../lib/presence/PresenceProvider'
import { renderInRoom, roundsSent, someoneReads, viewsSent } from '../test/presenceRoom'
import { COACH_SILENCE_MS, COACH_TIMEOUT_MS } from './ReadAloud'
import { Paragraph } from './Paragraph'

const session = { token: 'eyJ.t', region: 'koreacentral', word_score: 60, hold: 31 }
vi.mock('../api', () => ({
  api: {
    // Filed as sent, the way the server answers.
    addReading: vi.fn(async (reading: object) => ({ id: 1, created_at: '2026-11-06T00:00:00Z', ...reading })),
    assessorToken: vi.fn(async () => session),
    confirmHold: vi.fn(),
    giveBackHold: vi.fn(),
  },
}))

const track = { stop: vi.fn(), enabled: true }
const microphone = { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream
Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: vi.fn(async () => microphone) }, configurable: true })
const getUserMedia = vi.mocked(navigator.mediaDevices.getUserMedia)

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
  giveBack: vi.fn(),
}
let emit: (e: LiveEvent) => void = () => undefined
type RoundOptions = Omit<LiveOptions, 'start'>
const connect = vi.fn(async (_paragraph: string, opts: RoundOptions): Promise<LiveConnection> => {
  emit = opts.onEvent
  return connection
})
vi.mock('../lib/liveClient', () => ({
  connectReadAloud: (paragraph: string, opts: RoundOptions) => connect(paragraph, opts),
  connectSummary: vi.fn(),
}))

const berified: AzureWord = {
  Word: 'verified',
  PronunciationAssessment: { AccuracyScore: 41, ErrorType: 'Mispronunciation' },
  Phonemes: [{ Phoneme: 'v', PronunciationAssessment: { AccuracyScore: 8, NBestPhonemes: [{ Phoneme: 'b', Score: 80 }] } }],
}
const verified: AzureWord = { Word: 'verified', PronunciationAssessment: { AccuracyScore: 88, ErrorType: 'None' } }

const paragraph = 'Researchers verified it.'

/** The paragraph on the page, idle: marks land on its words in place. */
function idleParagraph(active = false, saved: Shown[] = [], onStart = vi.fn(), onEnd = vi.fn()) {
  return (
    <Paragraph
      paragraph={{ id: 7, text: paragraph }}
      pieces={pairSentences([paragraph], [{ en: paragraph, ko: '연구자들이 확인했다.' }])[0]}
      spans={[]}
      summaries={[]}
      saved={saved}
      onSummary={vi.fn()}
      onReading={vi.fn()}
      active={active}
      onStart={onStart}
      onEnd={onEnd}
    />
  )
}

function renderIdle(active = false, saved: Shown[] = []) {
  const onStart = vi.fn()
  const onEnd = vi.fn()
  render(idleParagraph(active, saved, onStart, onEnd))
  return { onStart, onEnd }
}

/** The paragraph as the article holds it: a round once filed comes back as the paragraph's saved marks. */
function renderFiling() {
  const onEnd = vi.fn()
  function Filing() {
    const [saved, setSaved] = useState<Shown[]>([])
    return (
      <Paragraph
        paragraph={{ id: 7, text: paragraph }}
        pieces={pairSentences([paragraph], [{ en: paragraph, ko: '연구자들이 확인했다.' }])[0]}
        spans={[]}
        summaries={[]}
        saved={saved}
        onSummary={vi.fn()}
        onReading={(reading) => setSaved(reading.corrections ?? [])}
        active={false}
        onStart={vi.fn()}
        onEnd={onEnd}
      />
    )
  }
  render(<Filing />)
  return { onEnd }
}

/** Azure stops a moment after it is asked, handing over what it still held as it goes. Returns how to let it finish. */
function stopLate() {
  let finish = () => undefined
  assessor.stop.mockImplementationOnce(
    () =>
      new Promise<undefined>((resolve) => {
        finish = () => {
          segment([berified], 'Researchers berified')
          resolve(undefined)
        }
      }),
  )
  return () => act(async () => finish())
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
  for (const fn of [connection.correct, connection.close, connection.dispose, connection.giveBack]) fn.mockClear()
  getUserMedia.mockClear()
  vi.mocked(api.confirmHold).mockClear()
  vi.mocked(api.giveBackHold).mockClear()
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
          paragraph_id: 7,
          user_text: 'Researchers berified it.',
          corrections: [expect.objectContaining({ word: 'verified', heard: 'b for v', fix: 'v', repeated_ok: false, at: 1 })],
        }),
      ),
    )
  })

  it('keeps the round done for the others when a last segment lands while Azure stops', async () => {
    const { socket } = renderInRoom(idleParagraph())
    await startRound()
    // Azure hands over what it still held as it stops.
    assessor.stop.mockImplementationOnce(async () => {
      segment([berified], 'Researchers berified')
      return undefined
    })
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(vi.mocked(api.addReading)).toHaveBeenCalled())
    expect(roundsSent(socket).at(-1)).toMatchObject({ paragraph: 7, phase: 'done', findings: [expect.objectContaining({ word: 'verified' })] })
  })

  it('says the round is over when the page is left, even if Azure hands over more as it stops', async () => {
    const { socket, rerender } = renderInRoom(idleParagraph())
    await startRound()
    const finish = stopLate()
    rerender(
      <PresenceProvider sessionId={3}>
        <p />
      </PresenceProvider>,
    )
    await finish()
    expect(roundsSent(socket).at(-1)).toBeNull()
  })

  it('says the round is over on Close, even if Azure hands over more as it stops', async () => {
    const { socket } = renderInRoom(idleParagraph())
    await startRound()
    const finish = stopLate()
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await finish()
    expect(roundsSent(socket).at(-1)).toBeNull()
    expect(screen.queryByRole('button', { name: 'verified: b for v' })).not.toBeInTheDocument()
  })

  it('keeps one audio element while someone else\'s round comes and goes, so a coach I hear goes on', () => {
    const { socket, container } = renderInRoom(idleParagraph())
    const audio = container.querySelector('.read-aloud audio')
    someoneReads(socket, { paragraph: 7, phase: 'done', heard: 'Researchers verified it.', findings: [] })
    expect(screen.getByRole('status')).toHaveTextContent('Someone finished')
    expect(container.querySelector('.read-aloud audio')).toBe(audio)
    someoneReads(socket, null)
    expect(container.querySelector('.read-aloud audio')).toBe(audio)
  })

  it('files a clean round too, so the old marks do not come back, and returns to idle on Close', async () => {
    const { onEnd } = renderIdle()
    await startRound()
    act(() => segment([verified], 'Researchers verified it.'))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())
    await waitFor(() => expect(vi.mocked(api.addReading)).toHaveBeenCalledWith(expect.objectContaining({ corrections: [] })))

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onEnd).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /b for v/ })).not.toBeInTheDocument()
  })

  it('keeps the marks after Close, still clickable, with Read again on offer', async () => {
    const { onEnd } = renderFiling()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onEnd).toHaveBeenCalled()

    expect(screen.getByRole('button', { name: 'Read again' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalled())
    expect(screen.getByRole('note', { name: 'verified' })).toHaveTextContent("You said /b/. It's /v/.")
  })

  it('keeps the sentence in the article, marks and all, so it still flips to its Korean', async () => {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    const sentence = screen.getByRole('button', { name: paragraph })
    expect(sentence).toContainElement(screen.getByRole('button', { name: 'verified: b for v' }))

    await userEvent.click(sentence)
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('연구자들이 확인했다.')
    expect(screen.queryByRole('button', { name: 'verified: b for v' })).not.toBeInTheDocument()
  })

  it('opens a clicked mark without flipping its sentence to the Korean', async () => {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    const sentence = screen.getByRole('button', { name: paragraph })
    const hit = screen.getByRole('button', { name: 'verified: b for v' })

    await userEvent.click(hit)
    fireEvent.animationEnd(sentence)
    hit.focus()
    await userEvent.keyboard('{Enter}')
    fireEvent.animationEnd(sentence)

    expect(sentence).not.toHaveTextContent('연구자들이 확인했다.')
    expect(screen.getByRole('note', { name: 'verified' })).toBeInTheDocument()
  })

  it('keeps Read aloud and Summarize in one row right under the text, with the round below it', async () => {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))

    const row = screen.getByRole('button', { name: 'Summarize' }).parentElement!
    expect(row.previousElementSibling).toHaveTextContent(paragraph)
    expect(row).toContainElement(screen.getByRole('button', { name: 'Read again' }))
    expect(row.compareDocumentPosition(screen.getByRole('note', { name: 'verified' }))).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('releases the microphone when the assessor is off', async () => {
    vi.mocked(api.assessorToken).mockRejectedValueOnce(new Error('Read aloud is off: set AZURE_SPEECH_KEY in Settings'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('Read aloud is off: set AZURE_SPEECH_KEY in Settings')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Could not start')
    expect(startAssessor).not.toHaveBeenCalled()
    expect(track.stop).toHaveBeenCalled()
  })

  it('asks for the microphone before it asks for the token', async () => {
    renderIdle()
    await startRound()
    expect(getUserMedia.mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.assessorToken).mock.invocationCallOrder[0])
  })

  it('takes no token when the microphone is refused', async () => {
    getUserMedia.mockRejectedValueOnce(new Error('Permission denied'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('Permission denied')).toBeInTheDocument()
    expect(api.assessorToken).not.toHaveBeenCalled()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('confirms once Azure is listening', async () => {
    renderIdle()
    await startRound()
    expect(api.confirmHold).toHaveBeenCalledExactlyOnceWith(31)
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('gives the price back when Azure will not start', async () => {
    startAssessor.mockRejectedValueOnce(new Error('no route to Azure'))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('no route to Azure')).toBeInTheDocument()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(31)
    expect(api.confirmHold).not.toHaveBeenCalled()
  })

  it('gives the price back when Azure fails during the round', async () => {
    renderIdle()
    await startRound()
    act(() => startAssessor.mock.calls[0][0].onError('Connection closed'))
    expect(screen.getByText('Assessor: Connection closed')).toBeInTheDocument()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(31)
  })

  it('takes no token when the page is left at the microphone prompt', async () => {
    let allow!: (m: MediaStream) => void
    getUserMedia.mockImplementationOnce(() => new Promise((resolve) => (allow = resolve)))
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    cleanup()
    await act(async () => allow(microphone))
    expect(api.assessorToken).not.toHaveBeenCalled()
    expect(track.stop).toHaveBeenCalled()
  })

  /** A finished reading's mark clicked, with fake timers on from then and the coach's call open. */
  async function callTheCoach() {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    vi.useFakeTimers({ shouldAdvanceTime: true })
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await vi.waitFor(() => expect(connect).toHaveBeenCalled())
    await act(() => vi.advanceTimersByTimeAsync(1))
  }

  it('gives the coach back when it never says a word', async () => {
    try {
      await callTheCoach()
      await act(() => vi.advanceTimersByTimeAsync(COACH_TIMEOUT_MS + 1))
      expect(connection.giveBack).toHaveBeenCalledOnce()
      expect(connection.close).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps the coach price once it has spoken', async () => {
    try {
      await callTheCoach()
      act(() => emit({ type: 'session.output_transcript.delta', delta: 'You said /b/.' }))
      await act(() => vi.advanceTimersByTimeAsync(COACH_TIMEOUT_MS + 1))
      expect(connection.giveBack).not.toHaveBeenCalled()
      expect(connection.close).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  /** The reading done with, and the coach's call open on its mark. */
  async function callWithRealTimers() {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalledOnce())
    await act(async () => undefined)
  }

  it('a second click gives back a connected coach that has said nothing', async () => {
    await callWithRealTimers()
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalledTimes(2))
    expect(connection.giveBack).toHaveBeenCalledOnce()
  })

  it('a second click keeps the price of a coach that has spoken', async () => {
    await callWithRealTimers()
    act(() => emit({ type: 'session.output_transcript.delta', delta: 'You said /b/.' }))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalledTimes(2))
    expect(connection.giveBack).not.toHaveBeenCalled()
  })

  it('leaving the page gives back a connected coach that has said nothing', async () => {
    await callWithRealTimers()
    cleanup()
    expect(connection.giveBack).toHaveBeenCalledOnce()
  })

  it('gives the price back once though Azure both reports and refuses', async () => {
    startAssessor.mockImplementationOnce(async (opts: AssessorOptions) => {
      opts.onError('Connection closed')
      throw new Error('no route to Azure')
    })
    renderIdle()
    await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText('no route to Azure')).toBeInTheDocument()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(31)
  })

  it('confirms nothing it has already given back', async () => {
    startAssessor.mockImplementationOnce(async (opts: AssessorOptions) => {
      opts.onError('Connection closed')
      return assessor
    })
    renderIdle()
    await startRound()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(31)
    expect(api.confirmHold).not.toHaveBeenCalled()
  })

  it('a second click abandons a call still connecting', async () => {
    connect.mockImplementationOnce(() => new Promise(() => undefined))
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalledOnce())
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    await waitFor(() => expect(connect).toHaveBeenCalledTimes(2))
    expect(connect.mock.calls[0][1].signal!.aborted).toBe(true)
    expect(connect.mock.calls[1][1].signal!.aborted).toBe(false)
  })

  it('is disabled while another paragraph holds the microphone', () => {
    renderIdle(true)
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled()
  })
})

describe('ReadAloud saved marks', () => {
  const mark: Shown = {
    word: 'verified',
    heard: 'b for v',
    fix: 'v',
    at: 1,
    score: 41,
    sounds: [{ phoneme: 'v', score: 8, weak: true, heard: 'b' }],
    repeated_ok: false,
  }

  it('shows the last round\'s marks on arrival, and opens a card from one without a round', async () => {
    renderIdle(false, [mark])
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    expect(screen.getByRole('note', { name: 'verified' })).toHaveTextContent("You said /b/. It's /v/.")
    expect(screen.getByRole('button', { name: 'Read again' })).toBeEnabled()
  })

  it('after Close the paragraph shows the marks it is given again, not its own round\'s', async () => {
    renderIdle(false, [mark])
    await userEvent.click(screen.getByRole('button', { name: 'Read again' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Listening'))
    act(() => segment([verified], 'Researchers verified it.'))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(assessor.stop).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'verified: b for v' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByRole('button', { name: 'verified: b for v' })).toBeInTheDocument()
  })

  it('tells the others which word\'s card is open by its place in the paragraph', async () => {
    const { socket } = renderInRoom(idleParagraph(false, [mark]))
    await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
    expect(viewsSent(socket)).toEqual([{ key: 'mark:7', value: 1 }])
  })

  it('clears them once a new round starts', async () => {
    renderIdle(false, [mark])
    await userEvent.click(screen.getByRole('button', { name: 'Read again' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Listening'))
    expect(screen.queryByRole('button', { name: 'verified: b for v' })).not.toBeInTheDocument()
  })
})

describe('ReadAloud marks', () => {
  it('marks a finding on the paragraph and turns it green when the word comes back clean', async () => {
    renderIdle()
    await startRound()
    act(() => segment([berified], 'berified'))
    const hit = screen.getByRole('button', { name: 'verified: b for v' })
    expect(hit).toHaveClass('reading-hit')
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
