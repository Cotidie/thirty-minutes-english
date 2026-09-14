import '@testing-library/jest-dom/vitest'

// jsdom has no AnimationEvent. Without one, React DOM listens for the
// webkit-prefixed name only and a fired `animationend` never lands.
if (!('AnimationEvent' in window)) {
  Object.defineProperty(window, 'AnimationEvent', { value: window.Event, configurable: true })
}
