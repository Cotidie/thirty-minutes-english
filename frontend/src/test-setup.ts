import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'
import { FakeEventSource } from './test/fakeEventSource'

vi.mock('partysocket', async () => ({ WebSocket: (await import('./test/fakeWebSocket')).FakeWebSocket }))

// jsdom has no AnimationEvent. Without one, React DOM listens for the
// webkit-prefixed name only and a fired `animationend` never lands.
const w = window as unknown as Record<string, unknown>
if (!('AnimationEvent' in w)) w.AnimationEvent = Event

// jsdom has no IntersectionObserver either: a list drawn in chunks shows its first chunk and stops there.
if (!('IntersectionObserver' in w)) {
  w.IntersectionObserver = class {
    observe() {}
    disconnect() {}
  }
}

// Nor elementFromPoint, which a pointer event in any test reaches on the session page.
document.elementFromPoint = () => null

// jsdom has no EventSource either.
w.EventSource = FakeEventSource
