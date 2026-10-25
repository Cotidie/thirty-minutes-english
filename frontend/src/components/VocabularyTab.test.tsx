import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Example, VocabularyItem } from '../types'
import { VocabularyTab } from './VocabularyTab'
import { api } from '../api'

vi.mock('../api', () => ({
  api: {
    addExample: vi.fn(),
    redrawPicture: vi.fn(),
    speak: vi.fn(async () => new Blob(['WAV'])),
    pictureStyles: vi.fn(async () => ({
      current: 'photo',
      options: [
        { id: 'photo', label: '', description: '', efforts: null },
        { id: 'comic', label: '', description: 'comic panel', efforts: null },
      ],
    })),
  },
}))
vi.mock('../lib/liveClient', () => ({ connectExample: vi.fn() }))

const none: Example[] = []

const items = [
  { id: 31, word: 'ubiquitous', pos: 'adjective', definition: 'present everywhere', example: 'Phones are ubiquitous.' },
  { id: 32, word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated the risk.' },
]

describe('VocabularyTab', () => {
  it('redraws one word at once in the style picked above the cards and hands the new item up', async () => {
    const drawn = [{ ...items[0], scene: 'phones on a train', image: 'a.png' }, items[1]]
    const fresh = { ...drawn[0], scene: 'phones at a dinner table', image: 'b.png' }
    vi.mocked(api.redrawPicture).mockResolvedValue(fresh)
    const onPicture = vi.fn()
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={onPicture} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'New picture for mitigate' })).not.toBeInTheDocument() // no scene yet
    expect(await screen.findByRole('radio', { name: 'photo' })).toHaveAttribute('aria-checked', 'true') // the configured style
    await userEvent.click(screen.getByRole('button', { name: 'New picture for ubiquitous' }))
    expect(api.redrawPicture).toHaveBeenLastCalledWith(3, 0, 'practice', 'photo')

    await userEvent.click(screen.getByRole('radio', { name: 'comic panel' }))
    await userEvent.click(screen.getByRole('button', { name: 'New picture for ubiquitous' }))
    expect(api.redrawPicture).toHaveBeenLastCalledWith(3, 0, 'practice', 'comic')
    expect(onPicture).toHaveBeenCalledWith(0, fresh)
  })

  it('counts the seconds over the picture while a redraw is on its way', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const drawn = [{ ...items[0], scene: 'phones on a train', image: 'a.png' }, items[1]]
    let finish: (item: VocabularyItem) => void = () => undefined
    vi.mocked(api.redrawPicture).mockReturnValue(new Promise((resolve) => (finish = resolve)))
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'New picture for ubiquitous' }))
    expect(screen.getByRole('status')).toHaveTextContent('Drawing… 0s')
    await act(() => vi.advanceTimersByTimeAsync(2100))
    expect(screen.getByRole('status')).toHaveTextContent('Drawing… 2s')
    await act(async () => finish({ ...drawn[0], image: 'b.png' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    vi.useRealTimers()
  })

  it('keeps the Korean word hidden behind a pill until it is tapped, without opening the meaning', async () => {
    const withKorean = [{ ...items[0], korean: '어디에나 있는' }, items[1]]
    render(<VocabularyTab items={withKorean} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    expect(screen.queryByText('어디에나 있는')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Korean for mitigate' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Korean for ubiquitous' }))
    expect(screen.getByRole('button', { name: 'Hide the Korean for ubiquitous' })).toHaveTextContent('어디에나 있는')
    expect(screen.getAllByText('Tap to check the meaning')).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Hide the Korean for ubiquitous' }))
    expect(screen.queryByText('어디에나 있는')).not.toBeInTheDocument()
  })

  it('shows the synonyms only with the definition, and no line when a word has none', async () => {
    const withSynonyms = [{ ...items[0], synonyms: ['everywhere', 'common'] }, items[1]]
    render(<VocabularyTab items={withSynonyms} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    expect(screen.queryByText(/everywhere, common/)).not.toBeInTheDocument()
    const [first, second] = screen.getAllByRole('button', { name: 'Tap to check the meaning' })
    await userEvent.click(first)
    expect(first).toHaveTextContent('present everywhere≈ everywhere, common')
    await userEvent.click(second)
    expect(second).toHaveTextContent(/^make less severe$/)
  })

  it('opens the scene caption over the picture with the word marked, without opening the meaning', async () => {
    const drawn = [{ ...items[0], scene: 'phones on a train', caption: 'Everyone on the train holds a phone: phones are ubiquitous.', image: 'a.png' }, items[1]]
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'What the picture for mitigate shows' })).not.toBeInTheDocument() // no caption
    const note = screen.getByRole('note', { hidden: true })
    expect(note).not.toHaveClass('is-shown')

    await userEvent.click(screen.getByRole('button', { name: 'What the picture for ubiquitous shows' }))
    expect(note).toHaveClass('is-shown')
    expect(note.querySelector('mark')).toHaveTextContent('ubiquitous')
    expect(screen.getAllByText('Tap to check the meaning')).toHaveLength(2)

    await userEvent.click(note)
    expect(note).not.toHaveClass('is-shown')
  })

  it('opens on the example picture and flips to the practice picture, the only one with a Scene button', async () => {
    const drawn = [{ ...items[0], scene: 'phones on a train', caption: 'Phones are ubiquitous here.', image: 'p.png', example_image: 'e.png' }, items[1]]
    vi.mocked(api.redrawPicture).mockResolvedValue(drawn[0])
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    expect(screen.getByRole('img', { name: 'Phones are ubiquitous.' })).toHaveAttribute('src', '/api/images/e.png')
    expect(screen.queryByRole('button', { name: 'What the picture for ubiquitous shows' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'New picture for ubiquitous' }))
    expect(api.redrawPicture).toHaveBeenLastCalledWith(3, 0, 'example', 'photo') // the face on show

    await userEvent.click(screen.getByRole('button', { name: 'Show the practice picture for ubiquitous' }))
    expect(screen.getByRole('img', { name: 'phones on a train' })).toHaveAttribute('src', '/api/images/p.png')
    expect(screen.getByRole('button', { name: 'What the picture for ubiquitous shows' })).toBeInTheDocument()
    expect(screen.getAllByText('Tap to check the meaning')).toHaveLength(2) // flipping leaves the meaning shut

    await userEvent.click(screen.getByRole('button', { name: 'Show the example picture for ubiquitous' }))
    expect(screen.getByRole('img', { name: 'Phones are ubiquitous.' })).toBeInTheDocument()
  })

  it('holds a place for pictures still on their way and shows each as it lands', () => {
    const props = { sessionId: 3, onPicture: vi.fn(), starred: [], onToggleStar: vi.fn(), examples: none, onExample: vi.fn() }
    const { rerender } = render(<VocabularyTab items={items} arriving {...props} />)
    expect(screen.getAllByText('Drawing…')).toHaveLength(2)
    rerender(<VocabularyTab items={[{ ...items[0], example_image: 'e.png' }, items[1]]} arriving {...props} />)
    expect(screen.getByRole('img', { name: 'Phones are ubiquitous.' })).toHaveAttribute('src', '/api/images/e.png')
    expect(screen.getAllByText('Drawing…')).toHaveLength(1)
  })

  it('shows the picture drawn for a word, and nothing where there is none', () => {
    const drawn = [{ ...items[0], scene: 'a phone in every hand on a train', image: 'job-0.png' }, items[1]]
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    const picture = screen.getByRole('img', { name: 'a phone in every hand on a train' })
    expect(picture).toHaveAttribute('src', '/api/images/job-0.png')
    expect(screen.getAllByRole('img')).toHaveLength(1)
  })

  it('reads the example aloud on the speaker button without opening the meaning, and stops on a second press', async () => {
    const play = vi.fn(async () => undefined)
    const pause = vi.fn()
    vi.stubGlobal(
      'Audio',
      class {
        play = play
        pause = pause
        onended = null
      },
    )
    URL.createObjectURL = vi.fn(() => 'blob:x')
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)

    await userEvent.click(screen.getAllByRole('button', { name: 'Read the sentence aloud' })[1])
    expect(api.speak).toHaveBeenCalledWith('We mitigated the risk.')
    expect(play).toHaveBeenCalled()
    expect(screen.getAllByText('Tap to check the meaning')).toHaveLength(2)

    await userEvent.click(screen.getByRole('button', { name: 'Stop reading' }))
    expect(pause).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('reads the word itself aloud on the speaker button beside it, without opening the meaning', async () => {
    const play = vi.fn(async () => undefined)
    vi.stubGlobal(
      'Audio',
      class {
        play = play
        pause = vi.fn()
        onended = null
      },
    )
    URL.createObjectURL = vi.fn(() => 'blob:x')
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: 'Read mitigate aloud' }))
    expect(api.speak).toHaveBeenLastCalledWith('mitigate')
    expect(play).toHaveBeenCalled()
    expect(screen.getAllByText('Tap to check the meaning')).toHaveLength(2)
    vi.unstubAllGlobals()
  })

  it('shows the word and example but hides the definition until clicked', async () => {
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    const [word, marked] = screen.getAllByText('ubiquitous')
    expect(marked.tagName).toBe('MARK') // the word, marked in its example
    expect(marked.parentElement).toHaveTextContent('Phones are ubiquitous.')
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()

    await userEvent.click(word)
    expect(screen.getByText('present everywhere')).toBeInTheDocument()
    expect(screen.queryByText('make less severe')).not.toBeInTheDocument()
  })

  it('hides the definition again on a second click', async () => {
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    const card = screen.getByText('mitigate')
    await userEvent.click(card)
    expect(screen.getByText('make less severe')).toBeInTheDocument()
    await userEvent.click(card)
    expect(screen.queryByText('make less severe')).not.toBeInTheDocument()
  })

  it('stars a word without flipping its card', async () => {
    const onToggleStar = vi.fn()
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[32]} onToggleStar={onToggleStar} examples={none} onExample={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Star mitigate' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByRole('button', { name: 'Star ubiquitous' }))
    expect(onToggleStar).toHaveBeenCalledWith(31)
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()
  })

  it('gives each word a Practice button with its own sentences under it', () => {
    const examples: Example[] = [
      { id: 1, created_at: '', expression_id: null, vocabulary_id: 32, user_text: 'We mitigated the delay.', coach_text: 'We mitigated the delay. Natural.', seconds: 9 },
      { id: 2, created_at: '', expression_id: 31, vocabulary_id: null, user_text: 'An expression with the same id.', coach_text: 'x', seconds: 9 },
    ]
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={examples} onExample={vi.fn()} />)
    expect(screen.getAllByRole('button', { name: 'Practice' })).toHaveLength(2)
    expect(screen.getByText('We mitigated the delay.')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Sentences with mitigate' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Sentences with ubiquitous' })).not.toBeInTheDocument()
    expect(screen.queryByText('An expression with the same id.')).not.toBeInTheDocument()
  })
})
