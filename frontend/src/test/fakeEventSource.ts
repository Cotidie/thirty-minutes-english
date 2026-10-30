/** jsdom has no EventSource. This one lets a test open the stream, send events, and drop it. */
export class FakeEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  /** The streams still open: one is what the app promises per session. */
  static get open(): FakeEventSource[] {
    return FakeEventSource.instances.filter((source) => source.readyState !== FakeEventSource.CLOSED)
  }

  readonly url: string
  readyState = FakeEventSource.CONNECTING
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private readonly listeners = new Map<string, Set<() => void>>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(name: string, listener: () => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set())
    this.listeners.get(name)?.add(listener)
  }

  close() {
    this.readyState = FakeEventSource.CLOSED
  }

  /** The server sends an event. */
  send(name: string) {
    this.listeners.get(name)?.forEach((listener) => listener())
  }

  /** The stream comes up, for the first time or again. */
  connect() {
    this.readyState = FakeEventSource.OPEN
    this.onopen?.()
  }

  /** The stream drops. `fatal` is an answer that is not a stream, which a browser does not retry. */
  drop(fatal = false) {
    this.readyState = fatal ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING
    this.onerror?.()
  }
}
