import { useCallback, useEffect, useRef } from 'react'

/**
 * What the server's event stream says: which resource of an open session to read again over REST.
 * The stream holds no data, and this file is the only place that connects to it.
 */
export type SessionChange = 'session' | 'stars' | 'note' | 'records'

const CHANGES: SessionChange[] = ['session', 'stars', 'note', 'records']
const REOPEN_MS = 5000
/** The server speaks at least every 25 seconds. A connection that died quietly tells a browser nothing, so this does. */
const SILENCE_LIMIT_MS = 60000
/** Coming back to the page after this long without a word, the connection is not worth trusting. */
const QUIET_ON_RETURN_MS = 30000

type Heard = SessionChange | 'gone'

/** One stream per open session, however many hooks read from it. */
class Channel {
  private readonly listeners = new Map<Heard, Set<() => void>>()
  private source: EventSource | null = null
  private reopen: ReturnType<typeof setTimeout> | undefined
  private watchdog: ReturnType<typeof setTimeout> | undefined
  private lastHeard = 0
  private readonly sessionId: number

  constructor(sessionId: number) {
    this.sessionId = sessionId
    window.addEventListener('online', this.restart)
    document.addEventListener('visibilitychange', this.returned)
    this.open()
  }

  private readonly restart = () => {
    this.source?.close()
    clearTimeout(this.reopen)
    this.open()
  }

  private readonly returned = () => {
    if (document.visibilityState === 'visible' && Date.now() - this.lastHeard >= QUIET_ON_RETURN_MS) this.restart()
  }

  private heardFromServer() {
    this.lastHeard = Date.now()
    clearTimeout(this.watchdog)
    this.watchdog = setTimeout(this.restart, SILENCE_LIMIT_MS)
  }

  private open() {
    const source = new EventSource(`/api/sessions/${this.sessionId}/events`)
    this.source = source
    this.heardFromServer()
    source.addEventListener('alive', () => this.heardFromServer())
    for (const change of CHANGES) {
      source.addEventListener(change, () => {
        this.heardFromServer()
        this.hear(change)
      })
    }
    source.addEventListener('gone', () => {
      this.close()
      this.hear('gone')
    })
    // Nothing missed while down is sent again, so every connection starts from what the server has now.
    source.onopen = () => {
      this.heardFromServer()
      CHANGES.forEach((change) => this.hear(change))
    }
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED) return // the browser is already trying again
      // An answer that is not a stream. Reading the session finds out why: a login gone, or the session gone.
      this.hear('session')
      this.reopen = setTimeout(() => this.open(), REOPEN_MS)
    }
  }

  private hear(what: Heard) {
    this.listeners.get(what)?.forEach((listener) => listener())
  }

  listen(what: Heard, listener: () => void) {
    if (!this.listeners.has(what)) this.listeners.set(what, new Set())
    this.listeners.get(what)?.add(listener)
  }

  /** Whether anyone is left. */
  stopListening(what: Heard, listener: () => void): boolean {
    this.listeners.get(what)?.delete(listener)
    return [...this.listeners.values()].some((set) => set.size > 0)
  }

  close() {
    clearTimeout(this.reopen)
    clearTimeout(this.watchdog)
    window.removeEventListener('online', this.restart)
    document.removeEventListener('visibilitychange', this.returned)
    this.source?.close()
  }
}

const channels = new Map<number, Channel>()

function listen(sessionId: number, what: Heard, listener: () => void): () => void {
  const channel = channels.get(sessionId) ?? new Channel(sessionId)
  channels.set(sessionId, channel)
  channel.listen(what, listener)
  return () => {
    if (channel.stopListening(what, listener)) return
    channel.close()
    channels.delete(sessionId)
  }
}

/** The latest of a value that changes every render, for an effect that should not start over for it. */
function useLatest<T>(value: T) {
  const latest = useRef(value)
  useEffect(() => {
    latest.current = value
  })
  return latest
}

/**
 * The one way to read a session's data: `read` over REST at first, again when `change` is announced, and
 * again whenever the stream comes up, each result going to `show`. One read runs at a time, and changes
 * during it make one more after it, so an old answer never lands on a newer one. What lands after the
 * session is left is dropped. Returns a way to ask for another read, in the same line.
 */
export function useSessionResource<T>(
  sessionId: number,
  change: SessionChange,
  read: () => Promise<T>,
  show: (value: T) => void,
  onError?: (error: Error) => void,
): () => void {
  const latest = useLatest({ read, show, onError })
  const readNow = useRef<() => void>(() => undefined)

  useEffect(() => {
    let live = true
    let reading = false
    let again = false

    const run = () => {
      if (reading) {
        again = true
        return
      }
      reading = true
      latest.current
        .read()
        .then((value) => {
          if (live) latest.current.show(value)
        })
        .catch((error: Error) => {
          if (live) latest.current.onError?.(error)
        })
        .finally(() => {
          reading = false
          if (live && again) {
            again = false
            run()
          }
        })
    }

    readNow.current = run
    const stop = listen(sessionId, change, run)
    run()
    return () => {
      live = false
      stop()
    }
  }, [sessionId, change, latest])

  return useCallback(() => readNow.current(), [])
}

/** Tells when the session was deleted, or this account can no longer open it. */
export function useSessionGone(sessionId: number, onGone: () => void): void {
  const latest = useLatest(onGone)
  useEffect(() => listen(sessionId, 'gone', () => latest.current()), [sessionId, latest])
}
