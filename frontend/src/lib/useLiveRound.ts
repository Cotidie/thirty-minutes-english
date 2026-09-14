import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import type { LiveConnection, LiveOptions } from './liveClient'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from './liveSession'

export type RoundOptions = Omit<LiveOptions, 'start'>
export type Connect = (opts: RoundOptions) => Promise<LiveConnection>
export type Keep = (round: LiveState) => Promise<void>

/** How long the coach stays quiet before we take the round as finished. */
export const SILENCE_MS = 5000

export interface LiveRound {
  state: LiveState | null
  saved: boolean
  microphone: MediaStream | null
  /** Opens a round. Also the retry: drops whatever was said and opens a fresh one. */
  start(): Promise<void>
  /** Ends the round; the transcript stays up until saved or dismissed. */
  close(): void
  /** Drops the round and its transcript. */
  dismiss(): void
  /** Hands the transcript to `keep`. Resolves true once it is written. */
  save(): Promise<boolean>
}

/**
 * One GPT-Live round behind a button: open, listen, close on its own once the
 * coach has been quiet, then wait to be told whether to keep the transcript.
 * The component owns the <audio> element the coach's voice plays through.
 */
export function useLiveRound(audio: RefObject<HTMLAudioElement | null>, connect: Connect, keep: Keep): LiveRound {
  const [state, setState] = useState<LiveState | null>(null)
  const [saved, setSaved] = useState(false)
  const [microphone, setMicrophone] = useState<MediaStream | null>(null)
  const connRef = useRef<LiveConnection | null>(null)
  const latest = useRef<LiveState | null>(null)
  const silence = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handlers = useRef({ connect, keep })

  // Handlers close over props that change; the round always calls the newest.
  useEffect(() => {
    handlers.current = { connect, keep }
    latest.current = state
  })

  const clearSilence = () => {
    if (silence.current) clearTimeout(silence.current)
    silence.current = null
  }

  useEffect(() => () => {
    clearSilence()
    connRef.current?.dispose()
  }, [])

  const save = useCallback(async () => {
    const round = latest.current
    if (!round) return false
    setSaved(true)
    try {
      await handlers.current.keep(round)
      return true
    } catch (e) {
      setSaved(false)
      setState((s) => (s ? { ...s, error: e instanceof Error ? e.message : String(e) } : s))
      return false
    }
  }, [])

  const close = useCallback(() => {
    clearSilence()
    setMicrophone(null)
    setState((s) => (s ? { ...s, status: 'closing' } : s))
    connRef.current?.close()
  }, [])

  const start = useCallback(async () => {
    clearSilence()
    connRef.current?.dispose()
    connRef.current = null
    setMicrophone(null)
    setState(initialLiveState)
    setSaved(false)
    try {
      const conn = await handlers.current.connect({
        audio: audio.current!,
        onEvent: (event) => {
          setState((s) => applyLiveEvent(s ?? initialLiveState, event))
          if (event.type === 'session.output_transcript.delta') {
            clearSilence()
            silence.current = setTimeout(close, SILENCE_MS)
          }
        },
        onDisconnect: () => {
          setMicrophone(null)
          setState((s) => liveFailed(s ?? initialLiveState, 'Connection dropped.'))
        },
      })
      connRef.current = conn
      setMicrophone(conn.microphone)
    } catch (e) {
      setState((s) => liveFailed(s ?? initialLiveState, e instanceof Error ? e.message : String(e)))
    }
  }, [audio, close])

  const dismiss = useCallback(() => {
    clearSilence()
    connRef.current?.dispose()
    connRef.current = null
    setMicrophone(null)
    setState(null)
  }, [])

  return { state, saved, microphone, start, close, dismiss, save }
}

/** A round with nothing on one of the two lines has nothing to keep. */
export function hasBothLines(state: LiveState): boolean {
  return state.user.trim() !== '' && state.coach.trim() !== ''
}
