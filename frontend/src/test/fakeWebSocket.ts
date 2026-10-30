import { expect } from 'vitest'

/** Stands in for partysocket's WebSocket. It lets a test open the socket, hear what it sends, send to it, and drop it. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  /** The sockets not closed for good, whether connected or trying again. */
  static get open(): FakeWebSocket[] {
    return FakeWebSocket.instances.filter((socket) => !socket.closed)
  }

  /** The one socket a test expects, with what the page sent so far. */
  static get only(): FakeWebSocket {
    expect(FakeWebSocket.open).toHaveLength(1)
    return FakeWebSocket.open[0]
  }

  readonly OPEN = 1
  readonly url: string
  readonly options: { maxEnqueuedMessages?: number }
  readyState = 0
  sent: Record<string, unknown>[] = []
  private closed = false
  private readonly listeners = new Map<string, Set<(event: never) => void>>()

  constructor(url: string, _protocols?: unknown, options: { maxEnqueuedMessages?: number } = {}) {
    this.url = url
    this.options = options
    FakeWebSocket.instances.push(this)
  }

  addEventListener(name: string, listener: (event: never) => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set())
    this.listeners.get(name)?.add(listener)
  }

  send(text: string) {
    this.sent.push(JSON.parse(text) as Record<string, unknown>)
  }

  close() {
    this.closed = true
    this.readyState = 3
  }

  /** The connection comes up. */
  connect() {
    this.readyState = 1
    this.emit('open', {})
  }

  /** The server sends a message. */
  receive(message: object) {
    this.emit('message', { data: JSON.stringify(message) })
  }

  /** The connection drops with this code. Unless the page calls `close`, it counts as trying again. */
  drop(code = 1006) {
    this.readyState = 0
    this.emit('close', { code })
  }

  private emit(name: string, event: object) {
    this.listeners.get(name)?.forEach((listener) => listener(event as never))
  }
}
