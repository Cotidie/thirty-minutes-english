import '@testing-library/jest-dom/vitest'
import { FakeEventSource } from './test/fakeEventSource'

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

// jsdom has no EventSource either.
w.EventSource = FakeEventSource
