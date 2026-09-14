import '@testing-library/jest-dom/vitest'

// jsdom has no AnimationEvent. Without one, React DOM listens for the
// webkit-prefixed name only and a fired `animationend` never lands.
const w = window as unknown as Record<string, unknown>
if (!('AnimationEvent' in w)) w.AnimationEvent = Event
