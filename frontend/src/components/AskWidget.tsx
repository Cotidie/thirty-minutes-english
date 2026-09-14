import { useEffect, useRef } from 'react'
import { useMatch } from 'react-router-dom'
import { api } from '../api'
import { connectAsk } from '../lib/liveClient'
import type { LiveState } from '../lib/liveSession'
import { useMicLevel } from '../lib/micLevel'
import { hasBothLines, useLiveRound } from '../lib/useLiveRound'
import { MicMeter } from './MicMeter'

const STATUS_LABEL: Record<LiveState['status'], string> = {
  connecting: 'Connecting…',
  listening: 'Listening',
  closing: 'Wrapping up…',
  closed: 'Round over',
  failed: 'Could not start',
}

export function AskWidget() {
  const match = useMatch('/s/:id')
  const sessionId = match?.params.id ? Number(match.params.id) : null
  const audioRef = useRef<HTMLAudioElement>(null)
  const round = useLiveRound(
    audioRef,
    async (opts) => {
      const topic = sessionId === null ? null : await api.getSession(sessionId).then((s) => s.content.topic, () => null)
      return connectAsk(topic, opts)
    },
    /** Only what the user chose to keep: a misheard or useless round is thrown away. */
    async (r) => {
      await api.addAsk({ session_id: sessionId, user_text: r.user.trim(), coach_text: r.coach.trim(), seconds: r.seconds })
    },
  )
  const { state, saved, start, close, dismiss, save } = round
  const level = useMicLevel(round.microphone)
  const open = state !== null

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (!open) {
        if (e.key !== 'a') return
        e.preventDefault()
        void start()
        return
      }
      if (e.key === 'Escape') {
        if (state.status === 'listening') close()
        else dismiss()
      } else if (e.key === 'r') {
        e.preventDefault()
        void start()
      } else if (e.key === 'Enter' && state.status === 'closed' && !saved && hasBothLines(state)) {
        e.preventDefault()
        void save()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, dismiss, open, save, saved, start, state])

  return (
    <div className={`ask${open ? ' is-open' : ''}`}>
      <audio ref={audioRef} autoPlay />
      {state === null ? (
        <button type="button" className="ask-start" onClick={() => void start()} aria-keyshortcuts="a">
          <span className="ask-start-glyph" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className="ask-start-label">Ask<kbd>a</kbd></span>
        </button>
      ) : (
        <div className="ask-slip" role="dialog" aria-label="Ask the coach">
          <div className="ask-bar">
            {state.status === 'listening' && <MicMeter level={level} />}
            <span className="ask-status" role="status">
              {saved ? 'Saved' : STATUS_LABEL[state.status]}
            </span>
            {state.seconds > 0 && <span className="ask-seconds">{state.seconds}s</span>}
          </div>

          {state.error && <p className="ask-error">{state.error}</p>}

          {(state.user || state.coach) && (
            <dl className="ask-captions">
              <dt>You</dt>
              <dd>{state.user}</dd>
              <dt>Coach</dt>
              <dd>{state.coach}</dd>
            </dl>
          )}

          <div className="ask-actions">
            <span className="ask-hint">{hintFor(state, saved)}</span>
            <button type="button" onClick={() => void start()}>
              Retry <kbd>r</kbd>
            </button>
            {state.status === 'listening' ? (
              <button type="button" onClick={close}>
                Done
              </button>
            ) : (
              <button type="button" onClick={dismiss}>
                {saved ? 'Close' : 'Discard'}
              </button>
            )}
            {state.status === 'closed' && !saved && (
              <button type="button" className="ask-save" onClick={() => void save()} disabled={!hasBothLines(state)}>
                Save
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function hintFor(state: LiveState, saved: boolean): string {
  if (saved) return 'Kept for review'
  if (state.status === 'listening') return 'Missed your moment? Retry'
  if (state.status === 'closed') return hasBothLines(state) ? 'Enter to save, Esc to discard' : 'Nothing came through'
  return ''
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}
