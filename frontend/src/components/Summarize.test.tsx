import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { LiveConnection } from '../lib/liveClient'
import type { LiveEvent } from '../lib/liveSession'
import { SILENCE_MS, type RoundOptions } from '../lib/useLiveRound'
import type { Summary, SummaryFeedback } from '../types'
import { Paragraph } from './Paragraph'

const connection = { microphone: {} as MediaStream, say: vi.fn(), correct: vi.fn(), close: vi.fn(), dispose: vi.fn(), giveBack: vi.fn() }
let emit: (e: LiveEvent) => void = () => undefined
const connect = vi.fn(async (_paragraph: string, opts: RoundOptions): Promise<LiveConnection> => {
  emit = opts.onEvent
  return connection
})

vi.mock('../lib/liveClient', () => ({
  connectSummary: (paragraph: string, opts: RoundOptions) => connect(paragraph, opts),
  connectReadAloud: vi.fn(),
}))
vi.mock('../api', () => ({ api: { addSummary: vi.fn(), judgeSummaryAgain: vi.fn(), removeSummary: vi.fn(), speak: vi.fn() } }))

const paragraph = 'Seoul scrapped its trams in 1968. Now it is laying tracks again.'
const said = 'Seoul was remove the tram at 1968 and now making again.'
const feedback: SummaryFeedback = {
  missed: ['Why: trams cost less than subways.'],
  summary: 'Seoul got rid of its trams in 1968 and is now bringing them back.',
  fixes: [{ said: 'was remove', better: 'got rid of' }],
}

const summary = (over: Partial<Summary> = {}): Summary => ({
  id: 7,
  created_at: '',
  paragraph_id: 4,
  user_text: said,
  seconds: 20,
  status: 'done',
  feedback,
  error: null,
  speaker: 'jo',
  mine: true,
  ...over,
})
const judging = summary({ status: 'judging', feedback: null })

function renderParagraph(props: { summaries?: Summary[]; onSummary?: () => void; onStart?: () => void; onEnd?: () => void } = {}) {
  return render(
    <Paragraph
      paragraph={{ id: 4, text: paragraph }}
      pieces={[{ text: paragraph, start: 0, ko: null }]}
      spans={[]}
      summaries={props.summaries ?? []}
      saved={[]}
      onSummary={props.onSummary ?? vi.fn()}
      onReading={vi.fn()}
      active={false}
      onStart={props.onStart ?? vi.fn()}
      onEnd={props.onEnd ?? vi.fn()}
    />,
  )
}

/** Opens a round, says the summary, presses Done and lets the transcriber close. */
async function sayAndFinish() {
  await userEvent.click(screen.getByRole('button', { name: 'Summarize' }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
  act(() => emit({ type: 'session.input_transcript.delta', delta: said }))
  await userEvent.click(screen.getByRole('button', { name: 'Done' }))
  act(() => emit({ type: 'session.closed', usage: { seconds: 20 } }))
}

beforeEach(() => {
  connection.giveBack.mockClear()
  vi.mocked(api.addSummary).mockReset()
  vi.mocked(api.judgeSummaryAgain).mockReset()
  vi.mocked(api.removeSummary).mockReset()
})

it('frees the paragraph as soon as the summary is sent, before any feedback', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.mocked(api.addSummary).mockResolvedValue(judging)
  const onSummary = vi.fn()
  const onStart = vi.fn()
  const onEnd = vi.fn()
  const { container } = renderParagraph({ onSummary, onStart, onEnd })
  const text = container.querySelector('.paragraph > p')!

  await userEvent.click(screen.getByRole('button', { name: 'Summarize' }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
  expect(connect.mock.calls.at(-1)![0]).toBe(paragraph) // the transcriber is primed with its words
  expect(onStart).toHaveBeenCalledOnce()
  expect(text).toHaveTextContent(paragraph) // still there to look back at
  expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled() // one microphone

  // The listener answering does not end the round: the reader may only have paused.
  act(() => emit({ type: 'session.input_transcript.delta', delta: 'Seoul was remove the tram at 1968' }))
  act(() => emit({ type: 'session.output_transcript.delta', delta: 'Mm.' }))
  await act(() => vi.advanceTimersByTimeAsync(SILENCE_MS + 1000))
  expect(connection.close).not.toHaveBeenCalled()
  expect(api.addSummary).not.toHaveBeenCalled()
  act(() => emit({ type: 'session.input_transcript.delta', delta: ' and now making again.' }))

  await userEvent.click(screen.getByRole('button', { name: 'Done' }))
  act(() => emit({ type: 'session.closed', usage: { seconds: 20 } }))
  await vi.waitFor(() => expect(onSummary).toHaveBeenCalledWith(judging))
  expect(api.addSummary).toHaveBeenCalledExactlyOnceWith({ paragraph_id: 4, user_text: said, seconds: 20 })
  expect(screen.queryByRole('dialog', { name: 'Summarize this paragraph' })).toBeNull()
  expect(onEnd).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: 'Read aloud' })).toBeEnabled()
  expect(connection.giveBack).not.toHaveBeenCalled()
  vi.useRealTimers()
})

it('gives the voice back when the summary could not be sent', async () => {
  vi.mocked(api.addSummary).mockRejectedValue(new Error('Not enough credits: this needs 5 and you have 2.'))
  const onEnd = vi.fn()
  renderParagraph({ onEnd })
  await sayAndFinish()
  expect(await screen.findByText(/Not enough credits/)).toBeInTheDocument()
  expect(connection.giveBack).toHaveBeenCalledOnce()
  expect(onEnd).not.toHaveBeenCalled()
})

it('still gives the voice back when the summary could not be sent after the page was left', async () => {
  let refuse: (e: Error) => void = () => undefined
  vi.mocked(api.addSummary).mockReturnValue(new Promise((_, reject) => (refuse = reject)))
  const { unmount } = renderParagraph()
  await sayAndFinish()
  await vi.waitFor(() => expect(api.addSummary).toHaveBeenCalledOnce())
  unmount()
  expect(connection.giveBack).not.toHaveBeenCalled() // sent: the server has it, or will say why not
  await act(async () => refuse(new Error('Not enough credits: this needs 5 and you have 2.')))
  expect(connection.giveBack).toHaveBeenCalledOnce()
})

it('does not drop a summary that was sent before the page was left', async () => {
  let keep: (s: Summary) => void = () => undefined
  vi.mocked(api.addSummary).mockReturnValue(new Promise((resolve) => (keep = resolve)))
  const onSummary = vi.fn()
  const { unmount } = renderParagraph({ onSummary })
  await sayAndFinish()
  await vi.waitFor(() => expect(api.addSummary).toHaveBeenCalledOnce())
  unmount()
  await act(async () => keep(judging))
  expect(connection.giveBack).not.toHaveBeenCalled()
})

it('gives the voice back when the page is left before the summary is sent', async () => {
  const { unmount } = renderParagraph()
  await userEvent.click(screen.getByRole('button', { name: 'Summarize' }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
  act(() => emit({ type: 'session.input_transcript.delta', delta: said }))
  unmount()
  expect(connection.giveBack).toHaveBeenCalledOnce()
  expect(api.addSummary).not.toHaveBeenCalled()
})

it('shows a summary being judged under the paragraph', () => {
  renderParagraph({ summaries: [judging] })
  const [card] = within(screen.getByRole('list', { name: 'Summaries of this paragraph' })).getAllByRole('listitem')
  expect(within(card).getByText('You').nextElementSibling).toHaveTextContent(said)
  expect(within(card).getByText('Reading your summary against the paragraph…')).toBeInTheDocument()
  expect(within(card).queryByText('Model answer')).toBeNull()
  expect(screen.getByRole('button', { name: 'Summarize again' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Read aloud' })).toBeEnabled()
})

it('shows a failed judgment with Judge again and Remove', async () => {
  vi.mocked(api.judgeSummaryAgain).mockRejectedValueOnce(new Error('Not enough credits: this needs 5 and you have 2.'))
  vi.mocked(api.removeSummary).mockResolvedValue(undefined)
  renderParagraph({ summaries: [summary({ status: 'failed', feedback: null, error: 'feedback failed: down' })] })
  const [card] = within(screen.getByRole('list', { name: 'Summaries of this paragraph' })).getAllByRole('listitem')
  expect(within(card).getByText('feedback failed: down')).toBeInTheDocument()
  await userEvent.click(within(card).getByRole('button', { name: /^Judge again/ }))
  expect(api.judgeSummaryAgain).toHaveBeenCalledExactlyOnceWith(7)
  expect(await within(card).findByText('Not enough credits: this needs 5 and you have 2.')).toBeInTheDocument()
  await userEvent.click(within(card).getByRole('button', { name: 'Remove' }))
  expect(api.removeSummary).toHaveBeenCalledExactlyOnceWith(7)
})

it('turns Judge again and Remove off while one of them is under way', async () => {
  vi.mocked(api.judgeSummaryAgain).mockReturnValue(new Promise(() => undefined))
  renderParagraph({ summaries: [summary({ status: 'failed', feedback: null, error: 'feedback failed: down' })] })
  const again = screen.getByRole('button', { name: /^Judge again/ })
  await userEvent.click(again)
  expect(again).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Remove' })).toBeDisabled()
  await userEvent.click(again)
  expect(api.judgeSummaryAgain).toHaveBeenCalledOnce()
})

it('names who said each summary', () => {
  renderParagraph({ summaries: [summary({ id: 1, mine: false, speaker: 'mina' }), summary({ id: 2, mine: false, speaker: null })] })
  const list = screen.getByRole('list', { name: 'Summaries of this paragraph' })
  expect(within(list).getByText('mina')).toBeInTheDocument()
  expect(within(list).getByText('Someone')).toBeInTheDocument()
  expect(within(list).queryByText('You')).toBeNull()
})

it('shows a kept summary in the card it was judged in, set apart from the article text', () => {
  const kept = summary()
  render(
    <Paragraph
      paragraph={{ id: 4, text: paragraph }}
      pieces={[{ text: paragraph, start: 0, ko: null }]}
      spans={[]}
      summaries={[kept]}
      saved={[]}
      onSummary={vi.fn()}
      onReading={vi.fn()}
      active={false}
      onStart={vi.fn()}
      onEnd={vi.fn()}
    />,
  )
  const [card] = within(screen.getByRole('list', { name: 'Summaries of this paragraph' })).getAllByRole('listitem')
  expect(card).toHaveClass('slip')
  expect(within(card).getByText('You').nextElementSibling).toHaveTextContent(said)
  expect(within(card).getByText('Missed').nextElementSibling).toHaveTextContent(feedback.missed[0])
  expect(within(card).getByText('Say it better').nextElementSibling).toHaveTextContent('was remove → got rid of')
  expect(within(card).getByText('was remove')).toHaveClass('summary-said')  // grey, not struck through
  expect(within(card).getByText('Model answer').nextElementSibling).toHaveTextContent(feedback.summary)
  expect(screen.getByRole('button', { name: 'Summarize again' })).toBeEnabled()
})
