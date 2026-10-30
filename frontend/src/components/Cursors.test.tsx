import { act, render } from '@testing-library/react'
import { Profiler } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PresenceProvider } from '../lib/presence/PresenceProvider'
import { useCursorSender } from '../lib/presence/useCursorSender'
import { useTellMyTab } from '../lib/presence/useOthersOnTab'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { renderInRoom, WELCOME } from '../test/presenceRoom'
import { Cursors } from './Cursors'

const RECT = { left: 100, top: 200, width: 400, height: 100 }
const WITH_B = { ...WELCOME, people: [{ id: 'b', color: 1, tab: 0 }] }

function Page({ tab = 0 }: { tab?: number }) {
  useTellMyTab(tab)
  useCursorSender(tab)
  return (
    <>
      <div data-testid="word" data-presence-anchor="word:2" />
      <Cursors />
    </>
  )
}

function placeWord(rect: Partial<DOMRect> = RECT) {
  const word = document.querySelector<HTMLElement>('[data-presence-anchor="word:2"]')
  if (word) word.getBoundingClientRect = () => rect as DOMRect
  return word as HTMLElement
}

const cursors = () => document.querySelectorAll<HTMLElement>('.cursor')

function theyPoint(socket: FakeWebSocket, extra: object = {}) {
  act(() => socket.receive({ type: 'cursor', id: 'b', tab: 0, anchor: 'word:2', x: 0.5, y: 0.5, ...extra }))
}

function inRoom() {
  const rendered = renderInRoom(<Page />, WITH_B)
  placeWord()
  return rendered
}

describe('Cursors, what is drawn', () => {
  it('draws the cursor of someone on my tab in their color, where their anchor is on my screen', () => {
    const { socket } = inRoom()
    theyPoint(socket)
    expect(cursors()).toHaveLength(1)
    expect(cursors()[0].style.transform).toBe('translate(300px, 250px)')
    expect(cursors()[0].getAttribute('style')).toContain('--person-2')
  })

  it('draws nothing for someone on another tab', () => {
    const { socket } = inRoom()
    theyPoint(socket, { tab: 1 })
    expect(cursors()).toHaveLength(0)
  })

  it('takes their cursor away the moment they go to another tab, though the mouse has not moved', () => {
    const { socket } = inRoom()
    theyPoint(socket)
    act(() => socket.receive({ type: 'tab', id: 'b', tab: 1 }))
    expect(cursors()).toHaveLength(0)
    act(() => socket.receive({ type: 'tab', id: 'b', tab: 0 }))
    expect(cursors()).toHaveLength(1)
  })

  it('takes the cursor away when I go to another tab, and brings it back when I return', () => {
    const { socket, rerender } = inRoom()
    theyPoint(socket)
    rerender(
      <PresenceProvider sessionId={3}>
        <Page tab={1} />
      </PresenceProvider>,
    )
    expect(cursors()).toHaveLength(0)
    rerender(
      <PresenceProvider sessionId={3}>
        <Page tab={0} />
      </PresenceProvider>,
    )
    placeWord()
    act(() => window.dispatchEvent(new Event('scroll')))
    expect(cursors()).toHaveLength(1)
  })

  it('draws nothing when the anchor is not on my screen, and takes away one that was drawn', () => {
    const { socket } = inRoom()
    theyPoint(socket, { anchor: 'word:999' })
    expect(cursors()).toHaveLength(0)
    theyPoint(socket)
    expect(cursors()).toHaveLength(1)
    theyPoint(socket, { anchor: 'word:999' })
    expect(cursors()).toHaveLength(0)
  })

  it('draws nothing at the corner of the screen when the anchor has no size', () => {
    const { socket } = inRoom()
    placeWord({ left: 0, top: 0, width: 0, height: 0 })
    theyPoint(socket)
    expect(cursors()).toHaveLength(0)
  })

  it.each([
    [-500, 'is-above', 'translate(300px, 8px)'],
    [5000, 'is-below', `translate(300px, ${window.innerHeight - 8}px)`],
  ])('marks a cursor off my screen at %i, and keeps it in view', (top, mark, transform) => {
    const { socket } = inRoom()
    placeWord({ ...RECT, top })
    theyPoint(socket, { y: 0 })
    expect(cursors()[0]).toHaveClass(mark)
    expect(cursors()[0].style.transform).toBe(transform)
  })

  it('removes the cursor when they send none', () => {
    const { socket } = inRoom()
    theyPoint(socket)
    act(() => socket.receive({ type: 'cursor', id: 'b', tab: 0, anchor: null }))
    expect(cursors()).toHaveLength(0)
  })

  it('removes the cursor when they leave', () => {
    const { socket } = inRoom()
    theyPoint(socket)
    act(() => socket.receive({ type: 'left', id: 'b' }))
    expect(cursors()).toHaveLength(0)
  })

  it('follows the anchor when I scroll', () => {
    const { socket } = inRoom()
    theyPoint(socket)
    placeWord({ ...RECT, top: 100 })
    act(() => window.dispatchEvent(new Event('scroll')))
    expect(cursors()[0].style.transform).toBe('translate(300px, 150px)')
  })

  it('does not render React for a cursor', () => {
    const rendered = vi.fn()
    const socket = (() => {
      render(
        <PresenceProvider sessionId={3}>
          <Profiler id="cursors" onRender={rendered}>
            <Page />
          </Profiler>
        </PresenceProvider>,
      )
      const only = FakeWebSocket.only
      act(() => {
        only.connect()
        only.receive(WITH_B)
      })
      placeWord()
      return only
    })()
    rendered.mockClear()
    for (let i = 0; i < 100; i++) theyPoint(socket, { x: i / 100 })
    expect(cursors()).toHaveLength(1)
    expect(rendered).not.toHaveBeenCalled()
  })

  it('stays out of the way of the page', () => {
    inRoom()
    expect(document.querySelector('.cursors')).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('Cursors, what is sent', () => {
  function move(pointerType: string, clientX = 300, clientY = 250) {
    const event = new MouseEvent('pointermove', { clientX, clientY })
    Object.defineProperty(event, 'pointerType', { value: pointerType })
    act(() => {
      window.dispatchEvent(event)
    })
  }
  const cursorsSent = (socket: FakeWebSocket) => socket.sent.filter((m) => m.type === 'cursor')

  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    document.elementFromPoint = () => null
  })

  function sending() {
    const rendered = inRoom()
    const word = placeWord()
    document.elementFromPoint = vi.fn(() => word)
    return rendered
  }

  it('sends where the mouse is, as an anchor and fractions', () => {
    const { socket } = sending()
    move('mouse')
    expect(cursorsSent(socket)).toEqual([{ type: 'cursor', tab: 0, anchor: 'word:2', x: 0.5, y: 0.5 }])
  })

  it('sends a mouse at most 20 times a second', () => {
    const { socket } = sending()
    for (let i = 0; i < 100; i++) {
      move('mouse', 100 + i)
      act(() => vi.advanceTimersByTime(10))
    }
    expect(cursorsSent(socket).length).toBeGreaterThanOrEqual(18)
    expect(cursorsSent(socket).length).toBeLessThanOrEqual(21)
  })

  it('sends the last place after a burst, not only the first', () => {
    const { socket } = sending()
    move('mouse', 100)
    move('mouse', 500)
    act(() => vi.advanceTimersByTime(60))
    expect(cursorsSent(socket).at(-1)).toMatchObject({ x: 1 })
  })

  it('does not send a touch', () => {
    const { socket } = sending()
    move('touch')
    act(() => vi.advanceTimersByTime(100))
    expect(cursorsSent(socket)).toEqual([])
  })

  it('says there is no cursor when the mouse leaves the page', () => {
    const { socket } = sending()
    move('mouse')
    act(() => {
      document.documentElement.dispatchEvent(new Event('pointerleave'))
    })
    expect(cursorsSent(socket).at(-1)).toEqual({ type: 'cursor', tab: 0, anchor: null })
  })

  it('says there is no cursor when the page hides', () => {
    const { socket } = sending()
    move('mouse')
    const shown = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    shown.mockRestore()
    expect(cursorsSent(socket).at(-1)).toEqual({ type: 'cursor', tab: 0, anchor: null })
  })

  it('says there is no cursor once, however long the mouse stays over nothing', () => {
    const { socket } = sending()
    document.elementFromPoint = vi.fn(() => document.body)
    for (let i = 0; i < 5; i++) {
      move('mouse', i)
      act(() => vi.advanceTimersByTime(60))
    }
    expect(cursorsSent(socket)).toEqual([{ type: 'cursor', tab: 0, anchor: null }])
  })

  it('sends again when scrolling moves another place under a still mouse', () => {
    const { socket } = sending()
    move('mouse')
    act(() => vi.advanceTimersByTime(60))
    placeWord({ ...RECT, top: 150 })
    act(() => {
      window.dispatchEvent(new Event('scroll'))
      vi.advanceTimersByTime(60)
    })
    expect(cursorsSent(socket).at(-1)).toMatchObject({ y: 1 })
  })

  it('says where the mouse is on a new tab without waiting for it to move', () => {
    const { socket, rerender } = sending()
    move('mouse')
    act(() => vi.advanceTimersByTime(60))
    rerender(
      <PresenceProvider sessionId={3}>
        <Page tab={2} />
      </PresenceProvider>,
    )
    expect(cursorsSent(socket).at(-1)).toMatchObject({ type: 'cursor', tab: 2, anchor: 'word:2' })
  })

  it('sends nothing on a new tab when the mouse has not been on the page', () => {
    const { socket, rerender } = sending()
    rerender(
      <PresenceProvider sessionId={3}>
        <Page tab={2} />
      </PresenceProvider>,
    )
    act(() => vi.advanceTimersByTime(60))
    expect(cursorsSent(socket)).toEqual([])
  })

  it('sends nothing on a scroll when the mouse has not been on the page', () => {
    const { socket } = sending()
    act(() => {
      window.dispatchEvent(new Event('scroll'))
      vi.advanceTimersByTime(60)
    })
    expect(cursorsSent(socket)).toEqual([])
  })
})
