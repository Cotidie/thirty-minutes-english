import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { PresenceProvider } from '../lib/presence/PresenceProvider'
import { renderInRoom, someoneSets, viewsSent, WELCOME } from '../test/presenceRoom'
import { ArticleTab } from './ArticleTab'

vi.mock('../api', () => ({
  api: {
    addReading: vi.fn(async () => ({})),
    listSummaries: vi.fn(async () => []),
    listReadings: vi.fn(async () => []),
    assessorToken: vi.fn(async () => ({ token: 't', region: 'koreacentral', word_score: 60 })),
  },
}))
Object.defineProperty(navigator, 'mediaDevices', {
  value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [], getAudioTracks: () => [] })) },
  configurable: true,
})
vi.mock('../lib/assessor/azure', () => ({ startAzureAssessor: vi.fn(async () => ({ stop: vi.fn(async () => undefined) })) }))
vi.mock('../lib/liveClient', () => ({
  connectReadAloud: vi.fn(async () => ({ microphone: { getAudioTracks: () => [] }, say: vi.fn(), correct: vi.fn(), close: vi.fn(), dispose: vi.fn() })),
  connectSummary: vi.fn(),
}))

const article = {
  title: 'Twins',
  paragraphs: [
    { id: 1, text: 'Ambition is cheap. Upkeep is what actually pays.' },
    { id: 2, text: 'A modest twin delivers more value.' },
  ],
  questions: [
    { text: 'What pays?', evidence: ['Upkeep is what actually pays.'] },
    { text: 'Legacy question', evidence: [] },
  ],
}

/** The evidence as marked on the page, word by word. */
const markedText = () => [...document.querySelectorAll('mark')].map((m) => m.textContent).join('')

describe('ArticleTab', () => {
  it('marks the evidence in the body when a question is clicked, and clears it on a second click', async () => {
    render(<ArticleTab article={article} sessionId={3} />)
    expect(document.querySelector('mark')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(markedText()).toBe('Upkeep is what actually pays.')

    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(document.querySelector('mark')).toBeNull()
  })

  it('lists sources as links when present and hides the block when absent', () => {
    const { unmount } = render(
      <ArticleTab
        article={{ ...article, sources: [{ title: 'Kafka - Britannica', url: 'https://www.britannica.com/kafka' }] }}
        sessionId={3}
      />,
    )
    const link = screen.getByRole('link', { name: 'Kafka - Britannica' })
    expect(link).toHaveAttribute('href', 'https://www.britannica.com/kafka')
    expect(screen.getByText('britannica.com')).toBeInTheDocument()
    unmount()

    render(<ArticleTab article={article} sessionId={3} />)
    expect(screen.queryByText('Sources')).toBeNull()
  })

  it('renders a question without evidence as plain text', () => {
    render(<ArticleTab article={article} sessionId={3} />)
    expect(screen.queryByRole('button', { name: 'Legacy question' })).toBeNull()
    expect(screen.getByText('Legacy question')).toBeInTheDocument()
  })

  it('puts back the marks of each paragraph\'s latest reading, leaving out ones kept without a place', async () => {
    const mark = (word: string, at: number) => ({ word, heard: 'x for y', fix: 'f', at, score: 30, sounds: [], repeated_ok: false })
    const reading = (paragraph_id: number, corrections: ReturnType<typeof mark>[]) =>
      ({ id: 1, created_at: '', paragraph_id, user_text: '', seconds: 9, corrections })
    vi.mocked(api.listReadings).mockResolvedValueOnce([
      reading(1, [mark('Upkeep', 3)]),
      reading(1, [mark('Ambition', 0)]),
      reading(2, [mark('modest', -1)]),
    ])
    render(<ArticleTab article={article} sessionId={3} />)
    expect(await screen.findByRole('button', { name: 'Upkeep: x for y' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ambition: x for y' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'modest: x for y' })).toBeNull()
    expect(vi.mocked(api.listReadings)).toHaveBeenCalledWith(3)
  })

  it('shows each figure right under its paragraph, with its caption and where it came from', () => {
    const figures = [
      { id: 1, paragraph_id: 2, image: '6.png', caption: 'A tram stop in the rain.', source_url: null, credit: null },
      { id: 2, paragraph_id: 1, image: '5.png', caption: 'Trams on the Wirye line.', source_url: 'https://www.yna.co.kr/view/1', credit: 'Yonhap' },
    ]
    render(<ArticleTab article={{ ...article, figures }} sessionId={3} />)
    const [first, second] = screen.getAllByRole('figure')
    expect(within(first).getByRole('img', { name: 'Trams on the Wirye line.' })).toHaveAttribute('src', '/api/images/5.png')
    expect(within(first).getByRole('link', { name: 'Yonhap · yna.co.kr' })).toHaveAttribute('href', 'https://www.yna.co.kr/view/1')
    expect(first.previousElementSibling).toHaveTextContent('Upkeep is what actually pays.')
    expect(within(second).getByText('Drawn for this article')).toBeInTheDocument()
    expect(second.previousElementSibling).toHaveTextContent('A modest twin delivers more value.')
  })

  it('shows the cover right under the title', () => {
    const figures = [
      { id: 1, paragraph_id: 1, image: '5.png', caption: 'Trams on the Wirye line.', source_url: null, credit: null },
      { id: 2, paragraph_id: null, image: '7.png', caption: 'Seoul at rush hour.', source_url: null, credit: null },
    ]
    render(<ArticleTab article={{ ...article, figures }} sessionId={3} />)
    const [cover] = screen.getAllByRole('figure')
    expect(within(cover).getByRole('img', { name: 'Seoul at rush hour.' })).toHaveAttribute('src', '/api/images/7.png')
    expect(cover.previousElementSibling).toHaveClass('article-title')
  })

  it('offers Read aloud under each paragraph and lets only one paragraph hold the microphone', async () => {
    render(<ArticleTab article={article} sessionId={3} />)
    const buttons = screen.getAllByRole('button', { name: 'Read aloud' })
    expect(buttons).toHaveLength(2)

    await userEvent.click(buttons[0])
    expect(screen.getByRole('status')).toHaveTextContent(/Connecting|Listening/)
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled()
  })
})

describe('ArticleTab open question', () => {
  it('marks the question the article does not answer and leaves it unclickable', async () => {
    render(
      <ArticleTab
        article={{
          ...article,
          questions: [
            { text: 'What pays?', evidence: ['Upkeep is what actually pays.'] },
            { text: 'Would you fund a twin you could not maintain?', evidence: [] },
          ],
        }}
        sessionId={3}
      />,
    )
    expect(screen.getByRole('button', { name: 'What pays?' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Would you fund/ })).not.toBeInTheDocument()
    expect(screen.getByText('your take')).toBeInTheDocument()
  })

  it('flips a sentence to its Korean once the English has sunk, and back on the next click', async () => {
    const translated = {
      ...article,
      translation: [
        { en: 'Ambition is cheap.', ko: '야심은 싸다.' },
        { en: 'Upkeep is what actually pays.', ko: '유지가 진짜 돈이 든다.' },
      ],
    }
    render(<ArticleTab article={translated} sessionId={3} />)
    const sentence = screen.getByRole('button', { name: 'Upkeep is what actually pays.' })
    expect(screen.queryByText('유지가 진짜 돈이 든다.')).not.toBeInTheDocument()

    await userEvent.click(sentence)
    expect(sentence).toHaveClass('is-sinking')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('유지가 진짜 돈이 든다.')
    expect(sentence).toHaveClass('is-ko', 'is-rising')
    expect(sentence).toHaveAttribute('lang', 'ko')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveClass('is-still')

    await userEvent.click(sentence)
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('Upkeep is what actually pays.')
    expect(sentence).not.toHaveAttribute('lang')
    // The untranslated paragraph stays plain text, not a button.
    expect(screen.queryByRole('button', { name: 'A modest twin delivers more value.' })).not.toBeInTheDocument()
  })

  it('still marks evidence inside a translated sentence, and across two of them', async () => {
    const translated = {
      ...article,
      questions: [{ text: 'Both?', evidence: ['cheap. Upkeep is what'] }],
      translation: [
        { en: 'Ambition is cheap.', ko: '야심은 싸다.' },
        { en: 'Upkeep is what actually pays.', ko: '유지가 진짜 돈이 든다.' },
      ],
    }
    render(<ArticleTab article={translated} sessionId={3} />)
    await userEvent.click(screen.getByRole('button', { name: 'Both?' }))
    expect(markedText()).toBe('cheap. Upkeep is what')
  })
})

describe('ArticleTab with someone else in the session', () => {
  const translated = {
    ...article,
    translation: [
      { en: 'Ambition is cheap.', ko: '야심은 싸다.' },
      { en: 'Upkeep is what actually pays.', ko: '유지가 진짜 돈이 든다.' },
    ],
  }
  const scrolled = vi.fn()

  beforeEach(() => {
    scrolled.mockClear()
    Element.prototype.scrollIntoView = scrolled
  })
  afterEach(() => {
    delete (Element.prototype as Partial<Element>).scrollIntoView
  })

  it('flips a sentence the same way a click does', () => {
    const { socket } = renderInRoom(<ArticleTab article={translated} sessionId={3} />)
    const sentence = screen.getByRole('button', { name: 'Ambition is cheap.' })
    someoneSets(socket, 'sentence:1:0', 'ko')
    expect(sentence).toHaveClass('is-sinking')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('야심은 싸다.')
    expect(sentence).toHaveClass('is-ko', 'is-rising')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveClass('is-still')
    someoneSets(socket, 'sentence:1:0', 'en')
    expect(sentence).toHaveClass('is-sinking')
  })

  it('catches up once the animation ends with a value that came during it', () => {
    const { socket } = renderInRoom(<ArticleTab article={translated} sessionId={3} />)
    const sentence = screen.getByRole('button', { name: 'Ambition is cheap.' })
    someoneSets(socket, 'sentence:1:0', 'ko')
    fireEvent.animationEnd(sentence)
    someoneSets(socket, 'sentence:1:0', 'en')
    expect(sentence).toHaveClass('is-rising')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveClass('is-sinking')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('Ambition is cheap.')
  })

  it('tells them when I flip a sentence', async () => {
    const { socket } = renderInRoom(<ArticleTab article={translated} sessionId={3} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ambition is cheap.' }))
    expect(viewsSent(socket)).toEqual([{ key: 'sentence:1:0', value: 'ko' }])
  })

  it('shows a sentence already flipped when I come to the tab, with no animation', () => {
    const { rerender } = renderInRoom(<p />, { ...WELCOME, view: { 'sentence:1:0': 'ko' } })
    rerender(
      <PresenceProvider sessionId={3}>
        <ArticleTab article={translated} sessionId={3} />
      </PresenceProvider>,
    )
    expect(screen.getByText('야심은 싸다.')).toHaveClass('is-ko', 'is-still')
  })

  it('marks the passage of the question they picked, without scrolling me', () => {
    const { socket } = renderInRoom(<ArticleTab article={article} sessionId={3} />)
    someoneSets(socket, 'question', 0)
    expect(markedText()).toBe('Upkeep is what actually pays.')
    expect(scrolled).not.toHaveBeenCalled()
  })

  it('scrolls only the person who clicked the question', async () => {
    const { socket } = renderInRoom(<ArticleTab article={article} sessionId={3} />)
    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(scrolled).toHaveBeenCalledOnce()
    expect(viewsSent(socket)).toEqual([{ key: 'question', value: 0 }])
  })

  it('a question number that is not here marks nothing', () => {
    const { socket } = renderInRoom(<ArticleTab article={article} sessionId={3} />)
    someoneSets(socket, 'question', 99)
    expect(document.querySelector('mark')).toBeNull()
  })
})
