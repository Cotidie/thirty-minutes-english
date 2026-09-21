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
    pictureStyles: vi.fn(async () => ({ current: 'photo', choices: ['photo', 'comic'], labels: { comic: 'comic panel' } })),
  },
}))
vi.mock('../lib/liveClient', () => ({ connectExample: vi.fn() }))

const none: Example[] = []

const items = [
  { word: 'ubiquitous', pos: 'adjective', definition: 'present everywhere', example: 'Phones are ubiquitous.' },
  { word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated the risk.' },
]

describe('VocabularyTab', () => {
  it('redraws one word in a chosen style from its menu and hands the new item up', async () => {
    const drawn = [{ ...items[0], scene: 'phones on a train', image: 'a.png' }, items[1]]
    const fresh = { ...drawn[0], scene: 'phones at a dinner table', image: 'b.png' }
    vi.mocked(api.redrawPicture).mockResolvedValue(fresh)
    const onPicture = vi.fn()
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={onPicture} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'New picture for mitigate' })).not.toBeInTheDocument() // no scene yet
    await userEvent.click(screen.getByRole('button', { name: 'New picture for ubiquitous' }))
    const menu = await screen.findByRole('menu', { name: 'Picture style for ubiquitous' })
    expect(menu).toHaveTextContent('photo (current)')
    await userEvent.click(screen.getByRole('menuitem', { name: 'comic · comic panel' }))
    expect(api.redrawPicture).toHaveBeenCalledWith(3, 0, 'comic')
    expect(onPicture).toHaveBeenCalledWith(0, fresh)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('counts the seconds over the picture while a redraw is on its way', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const drawn = [{ ...items[0], scene: 'phones on a train', image: 'a.png' }, items[1]]
    let finish: (item: VocabularyItem) => void = () => undefined
    vi.mocked(api.redrawPicture).mockReturnValue(new Promise((resolve) => (finish = resolve)))
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'New picture for ubiquitous' }))
    await userEvent.click(screen.getByRole('menuitem', { name: /comic/ }))
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

  it('shows the picture drawn for a word, and nothing where there is none', () => {
    const drawn = [{ ...items[0], scene: 'a phone in every hand on a train', image: 'job-0.png' }, items[1]]
    render(<VocabularyTab items={drawn} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    const picture = screen.getByRole('img', { name: 'a phone in every hand on a train' })
    expect(picture).toHaveAttribute('src', '/api/images/job-0.png')
    expect(screen.getAllByRole('img')).toHaveLength(1)
  })

  it('shows the word and example but hides the definition until clicked', async () => {
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    expect(screen.getByText('ubiquitous')).toBeInTheDocument()
    expect(screen.getByText('Phones are ubiquitous.')).toBeInTheDocument()
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('ubiquitous'))
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
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={['mitigate']} onToggleStar={onToggleStar} examples={none} onExample={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Star mitigate' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByRole('button', { name: 'Star ubiquitous' }))
    expect(onToggleStar).toHaveBeenCalledWith('ubiquitous')
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()
  })

  it('gives each word a Practice button with its own sentences under it', () => {
    const examples: Example[] = [
      { id: 1, created_at: '', session_id: 3, expression: 'mitigate', user_text: 'We mitigated the delay.', coach_text: 'We mitigated the delay. Natural.', seconds: 9 },
    ]
    render(<VocabularyTab items={items} sessionId={3} onPicture={vi.fn()} starred={[]} onToggleStar={vi.fn()} examples={examples} onExample={vi.fn()} />)
    expect(screen.getAllByRole('button', { name: 'Practice' })).toHaveLength(2)
    expect(screen.getByText('We mitigated the delay.')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Sentences with mitigate' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Sentences with ubiquitous' })).not.toBeInTheDocument()
  })
})
