import { useCallback, useEffect, useRef } from 'react'

/**
 * What the server's event streams say: which resource to read again over REST, of an open session or of the
 * account. The streams hold no data, and this file is the only place that connects to them.
 */
export type SessionChange = 'session' | 'stars' | 'note' | 'records'
export type AccountChange = 'sessions'
type Change = SessionChange | AccountChange

const CHANGES: Change[] = ['session', 'stars', 'note', 'records', 'sessions']
const ACCOUNT_STREAM = '/api/me/events'
const REOPEN_MS = 5000
/** The server speaks at least every 25 seconds. A connection that died quietly tells a browser nothing, so this does. */
const SILENCE_LIMIT_MS = 60000
/** Coming back to the page after this long without a word, the connection is not worth trusting. */
const QUIET_ON_RETURN_MS = 30000

type Heard = Change | 'gone'

const sessionStream = (sessionId: number) => `/api/sessions/${sessionId}/events`

/** One connection per stream, however many hooks read from it. */
class Channel {
  private readonly listeners = new Map<Heard, Set<() => void>>()
  private source: EventSource | null = null
  private reopen: ReturnType<typeof setTimeout> | undefined
  private watchdog: ReturnType<typeof setTimeout> | undefined
  private lastHeard = 0
  private readonly url: string

  constructor(url: string) {
    this.url = url
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
    const source = new EventSource(this.url)
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
      // An answer that is not a stream. Reading finds out why: a login gone, or the session gone.
      this.hear('session')
      this.hear('sessions')
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

const channels = new Map<string, Channel>()

function listen(url: string, what: Heard, listener: () => void): () => void {
  const channel = channels.get(url) ?? new Channel(url)
  channels.set(url, channel)
  channel.listen(what, listener)
  return () => {
    if (channel.stopListening(what, listener)) return
    channel.close()
    channels.delete(url)
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
 * `read` over REST at first, again when `change` is announced, and again whenever the stream comes up, each
 * result going to `show`. One read runs at a time, and changes during it make one more after it, so an old
 * answer never lands on a newer one. What lands after leaving is dropped. Returns a way to ask for another
 * read, in the same line.
 */
function useStreamedResource<T>(
  url: string,
  change: Change,
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
    const stop = listen(url, change, run)
    run()
    return () => {
      live = false
      stop()
    }
  }, [url, change, latest])

  return useCallback(() => readNow.current(), [])
}

/** The one way to read a session's data. */
export function useSessionResource<T>(
  sessionId: number,
  change: SessionChange,
  read: () => Promise<T>,
  show: (value: T) => void,
  onError?: (error: Error) => void,
): () => void {
  return useStreamedResource(sessionStream(sessionId), change, read, show, onError)
}

/** The one way to read what belongs to the account rather than to one session. */
export function useAccountResource<T>(
  change: AccountChange,
  read: () => Promise<T>,
  show: (value: T) => void,
  onError?: (error: Error) => void,
): () => void {
  const readAgain = useStreamedResource(ACCOUNT_STREAM, change, read, show, onError)
  // This stream only ends with the login, and a read is what takes the page to the login form.
  useEffect(() => listen(ACCOUNT_STREAM, 'gone', readAgain), [readAgain])
  return readAgain
}

/** Tells when the session was deleted, or this account can no longer open it. */
export function useSessionGone(sessionId: number, onGone: () => void): void {
  const latest = useLatest(onGone)
  useEffect(() => listen(sessionStream(sessionId), 'gone', () => latest.current()), [sessionId, latest])
}
