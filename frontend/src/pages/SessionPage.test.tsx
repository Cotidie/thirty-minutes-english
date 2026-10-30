import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { FakeEventSource } from '../test/fakeEventSource'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { WELCOME } from '../test/presenceRoom'
import { SessionPage } from './SessionPage'

const session = {
  id: 3,
  created_at: '',
  topic: 'X',
  title: 'T',
  mine: false,
  shared_by: 'mina@example.com',
  content: {
    topic: 'X',
    expressions: [{ id: 1, phrase: 'a moving target', meaning: 'keeps changing', usage_note: 'n', examples: ['e1', 'e2'] }],
    article: { title: 'Title', paragraphs: [{ id: 1, text: 'Body.' }], questions: [], sources: [], translation: [] },
    vocabulary: [{ id: 2, word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated it.' }],
  },
}

vi.mock('../api', () => ({
  api: {
    getSession: vi.fn(async () => session),
    listJobs: vi.fn(async () => []),
    getStars: vi.fn(async () => ({ expressions: [], words: [] })),
    listExamples: vi.fn(async () => []),
    getNote: vi.fn(async () => ({ text: '' })),
    setNote: vi.fn(async (_id: number, text: string) => ({ text })),
    listReadings: vi.fn(async () => []),
    listSummaries: vi.fn(async () => []),
    swapExpression: vi.fn(async () => ({ id: 5, phrase: 'touch base', meaning: 'contact briefly', usage_note: 'n', examples: ['e3', 'e4'] })),
    addExpression: vi.fn(async () => ({ id: 6, phrase: 'circle back', meaning: 'return to it later', usage_note: 'n', examples: ['e5', 'e6'] })),
  },
}))
vi.mock('../lib/auth', () => ({
  useAuth: () => ({ me: { id: 1, email: 'a@example.com', is_admin: false, can_create: true } }),
}))
vi.mock('../lib/liveClient', () => ({ connectExample: vi.fn(), connectSummary: vi.fn() }))

function Hash() {
  return <output aria-label="hash">{useLocation().hash}</output>
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/s/:id" element={<><SessionPage /><Hash /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SessionPage', () => {
  it('opens on the tab named in the address, so a reload stays there', async () => {
    renderAt('/s/3#vocabulary')
    expect(await screen.findByText('mitigate')).toBeInTheDocument()
    expect(screen.queryByText('a moving target')).not.toBeInTheDocument()
  })

  it('names the picked tab in the address, and opens on Expressions without one', async () => {
    renderAt('/s/3')
    expect(await screen.findByText('a moving target')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Article/ }))
    expect(screen.getByLabelText('hash')).toHaveTextContent('#article')
  })

  it('stays on the tab it is on while the timer runs, past the end of a phase', async () => {
    renderAt('/s/3#vocabulary')
    await screen.findByText('mitigate')
    vi.useFakeTimers()
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Start 30 min' }))
      act(() => vi.advanceTimersByTime(11 * 60 * 1000))
      expect(screen.getByText('19:00')).toBeInTheDocument()
      expect(screen.getByLabelText('hash')).toHaveTextContent('#vocabulary')
      expect(screen.getByText('mitigate')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps one note on every tab and saves it; Summary leaves it to the Notes box', async () => {
    renderAt('/s/3')
    await screen.findByText('a moving target')

    await userEvent.click(screen.getByRole('button', { name: 'Open notes' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Notes' }), 'hedge 발음')
    expect(await screen.findByText('Saved', {}, { timeout: 2000 })).toBeInTheDocument()
    expect(vi.mocked(api.setNote)).toHaveBeenLastCalledWith(3, 'hedge 발음', false)

    await userEvent.click(screen.getByRole('button', { name: /Article/ }))
    expect(screen.getByRole('textbox', { name: 'Notes' })).toHaveValue('hedge 발음')

    await userEvent.click(screen.getByRole('button', { name: /Summary/ }))
    expect(screen.getByRole('textbox', { name: 'Notes' })).toHaveValue('hedge 발음')
    const content = document.querySelector('.content') as HTMLElement
    expect(within(content).queryByText('hedge 발음')).toBeNull()
  })

  it('swaps an expression in place for the one the server picked', async () => {
    renderAt('/s/3')
    await userEvent.click(await screen.findByRole('button', { name: 'Swap a moving target for another expression' }))
    expect(await screen.findByText('touch base')).toBeInTheDocument()
    expect(screen.queryByText('a moving target')).not.toBeInTheDocument()
    expect(api.swapExpression).toHaveBeenCalledWith(3, 1)
  })

  it('adds the expression the server picked after the others', async () => {
    renderAt('/s/3')
    await userEvent.click(await screen.findByRole('button', { name: 'Add another expression' }))
    expect(await screen.findByText('circle back')).toBeInTheDocument()
    expect(screen.getByText('a moving target')).toBeInTheDocument()
    expect(api.addExpression).toHaveBeenCalledWith(3)
  })
})

describe('SessionPage, with someone else in the session', () => {
  it('shows a new expression without a reload', async () => {
    renderAt('/s/3')
    expect(await screen.findByText('a moving target')).toBeInTheDocument()
    const changed = { ...session.content.expressions[0], id: 9, phrase: 'touch base' }
    vi.mocked(api.getSession).mockResolvedValueOnce({ ...session, content: { ...session.content, expressions: [changed] } } as never)
    act(() => FakeEventSource.open[0].send('session'))
    expect(await screen.findByText('touch base')).toBeInTheDocument()
    expect(screen.queryByText('a moving target')).not.toBeInTheDocument()
  })

  it('says so when the session goes away, and closes the stream', async () => {
    renderAt('/s/3')
    expect(await screen.findByText('a moving target')).toBeInTheDocument()
    act(() => FakeEventSource.open[0].send('gone'))
    expect(await screen.findByText('This session is no longer available.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to sessions' })).toHaveAttribute('href', '/')
    expect(FakeEventSource.open).toHaveLength(0)
  })

  it('says the same when the session cannot be found', async () => {
    vi.mocked(api.getSession).mockRejectedValueOnce(Object.assign(new Error('session not found'), { status: 404 }))
    renderAt('/s/3')
    expect(await screen.findByText('This session is no longer available.')).toBeInTheDocument()
  })

  it('keeps showing the session when a read fails for another reason', async () => {
    renderAt('/s/3')
    expect(await screen.findByText('a moving target')).toBeInTheDocument()
    vi.mocked(api.getSession).mockRejectedValueOnce(Object.assign(new Error('offline'), { status: 502 }))
    act(() => FakeEventSource.open[0].send('session'))
    await act(async () => {})
    expect(screen.getByText('a moving target')).toBeInTheDocument()
  })
})

describe('SessionPage with someone else in the session', () => {
  const HERE = 'Someone else is here'
  const tabNamed = (name: RegExp) => screen.getByRole('button', { name })

  async function open(people: object[] = [], path = '/s/3') {
    renderAt(path)
    await screen.findByRole('navigation', { name: 'Session parts' })
    const socket = FakeWebSocket.only
    act(() => {
      socket.connect()
      socket.receive({ ...WELCOME, people })
    })
    return socket
  }

  it('says which tab the other person is on, in their color', async () => {
    await open([{ id: 'b', color: 1, tab: 2 }])
    expect(within(tabNamed(/Vocabulary/)).getByRole('img', { name: HERE }).getAttribute('style')).toContain('--person-2')
    expect(within(tabNamed(/Article/)).queryByRole('img')).toBeNull()
  })

  it('moves the mark when they move, and takes it away when they leave', async () => {
    const socket = await open([{ id: 'b', color: 1, tab: 2 }])
    act(() => socket.receive({ type: 'tab', id: 'b', tab: 1 }))
    expect(within(tabNamed(/Vocabulary/)).queryByRole('img')).toBeNull()
    expect(within(tabNamed(/Article/)).getByRole('img', { name: HERE })).toBeInTheDocument()
    act(() => socket.receive({ type: 'left', id: 'b' }))
    expect(within(tabNamed(/Article/)).queryByRole('img')).toBeNull()
  })

  it('marks whoever comes in, once they say where they are', async () => {
    const socket = await open()
    act(() => socket.receive({ type: 'joined', id: 'b', color: 1, tab: null }))
    expect(screen.queryByRole('img', { name: HERE })).toBeNull()
    act(() => socket.receive({ type: 'tab', id: 'b', tab: 0 }))
    expect(within(tabNamed(/Expressions/)).getByRole('img', { name: HERE })).toBeInTheDocument()
  })

  it('tells the others which tab I am on, and again after reconnecting', async () => {
    const socket = await open([], '/s/3#article')
    expect(socket.sent).toEqual([{ type: 'tab', tab: 1 }])
    await userEvent.click(tabNamed(/Vocabulary/))
    expect(socket.sent).toEqual([{ type: 'tab', tab: 1 }, { type: 'tab', tab: 2 }])
    socket.sent = []
    act(() => {
      socket.drop()
      socket.connect()
      socket.receive(WELCOME)
    })
    expect(socket.sent).toEqual([{ type: 'tab', tab: 2 }])
  })

  it('shows one mark for one person on two connections, and one each for two people', async () => {
    await open([
      { id: 'b', color: 1, tab: 0 },
      { id: 'c', color: 1, tab: 0 },
      { id: 'd', color: 2, tab: 0 },
    ])
    expect(within(tabNamed(/Expressions/)).getAllByRole('img', { name: HERE })).toHaveLength(2)
  })

  it('marks the Summary tab too', async () => {
    await open([{ id: 'b', color: 0, tab: 3 }])
    expect(within(tabNamed(/Summary/)).getByRole('img', { name: HERE })).toBeInTheDocument()
  })

  it('goes round the colors past the last one', async () => {
    await open([{ id: 'b', color: 6, tab: 0 }])
    expect(within(tabNamed(/Expressions/)).getByRole('img', { name: HERE }).getAttribute('style')).toContain('--person-1')
  })
})
