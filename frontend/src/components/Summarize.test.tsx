import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { api } from '../api'
import type { LiveConnection } from '../lib/liveClient'
import type { LiveEvent } from '../lib/liveSession'
import { SILENCE_MS, type RoundOptions } from '../lib/useLiveRound'
import type { Summary, SummaryFeedback } from '../types'
import { Paragraph } from './Paragraph'

const connection = { microphone: {} as MediaStream, say: vi.fn(), correct: vi.fn(), close: vi.fn(), dispose: vi.fn() }
let emit: (e: LiveEvent) => void = () => undefined
const connect = vi.fn(async (_paragraph: string, opts: RoundOptions): Promise<LiveConnection> => {
  emit = opts.onEvent
  return connection
})

vi.mock('../lib/liveClient', () => ({
  connectSummary: (paragraph: string, opts: RoundOptions) => connect(paragraph, opts),
  connectReadAloud: vi.fn(),
}))
vi.mock('../api', () => ({ api: { summaryFeedback: vi.fn(), addSummary: vi.fn(), speak: vi.fn() } }))

const paragraph = 'Seoul scrapped its trams in 1968. Now it is laying tracks again.'
const said = 'Seoul was remove the tram at 1968 and now making again.'
const feedback: SummaryFeedback = {
  missed: ['Why: trams cost less than subways.'],
  summary: 'Seoul got rid of its trams in 1968 and is now bringing them back.',
  fixes: [{ said: 'was remove', better: 'got rid of' }],
}

it('keeps the paragraph in view while it is summed up, then on Done judges the summary and keeps it on its own', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const kept: Summary = { id: 5, created_at: '', session_id: 3, paragraph, user_text: said, feedback, seconds: 20 }
  vi.mocked(api.summaryFeedback).mockResolvedValue(feedback)
  vi.mocked(api.addSummary).mockResolvedValue(kept)
  const onSummary = vi.fn()
  const onStart = vi.fn()
  const onEnd = vi.fn()
  const { container } = render(
    <Paragraph
      paragraph={paragraph}
      pieces={[{ text: paragraph, start: 0, ko: null }]}
      spans={[]}
      sessionId={3}
      summaries={[]}
      saved={[]}
      onSummary={onSummary}
      active={false}
      onStart={onStart}
      onEnd={onEnd}
    />,
  )
  const text = container.querySelector('.paragraph > p')!

  await userEvent.click(screen.getByRole('button', { name: 'Summarize' }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
  expect(connect.mock.calls[0][0]).toBe(paragraph) // the transcriber is primed with its words
  expect(onStart).toHaveBeenCalledOnce()
  expect(text).toHaveTextContent(paragraph) // still there to look back at
  expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled() // one microphone

  // The listener answering does not end the round: the reader may only have paused.
  act(() => emit({ type: 'session.input_transcript.delta', delta: 'Seoul was remove the tram at 1968' }))
  act(() => emit({ type: 'session.output_transcript.delta', delta: 'Mm.' }))
  await act(() => vi.advanceTimersByTimeAsync(SILENCE_MS + 1000))
  expect(connection.close).not.toHaveBeenCalled()
  expect(api.summaryFeedback).not.toHaveBeenCalled()
  act(() => emit({ type: 'session.input_transcript.delta', delta: ' and now making again.' }))

  await userEvent.click(screen.getByRole('button', { name: 'Done' }))
  expect(screen.queryByRole('button', { name: 'Keep' })).toBeNull()
  act(() => emit({ type: 'session.closed', usage: { seconds: 20 } }))
  await vi.waitFor(() => expect(onSummary).toHaveBeenCalledWith(kept))
  expect(api.summaryFeedback).toHaveBeenCalledExactlyOnceWith(paragraph, said)
  expect(api.addSummary).toHaveBeenCalledWith({ session_id: 3, paragraph, user_text: said, feedback, seconds: 20 })
  // The slip closes; the kept card shows the judgment in its place.
  expect(screen.queryByRole('dialog', { name: 'Summarize this paragraph' })).toBeNull()
  expect(onEnd).toHaveBeenCalledOnce()
  vi.useRealTimers()
})

it('shows a kept summary in the card it was judged in, set apart from the article text', () => {
  const kept: Summary = { id: 7, created_at: '', session_id: 3, paragraph, user_text: said, feedback, seconds: 20 }
  render(
    <Paragraph
      paragraph={paragraph}
      pieces={[{ text: paragraph, start: 0, ko: null }]}
      spans={[]}
      sessionId={3}
      summaries={[kept]}
      saved={[]}
      onSummary={vi.fn()}
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
  expect(within(card).getByText('Model answer').nextElementSibling).toHaveTextContent(feedback.summary)
  expect(screen.getByRole('button', { name: 'Summarize again' })).toBeEnabled()
})
