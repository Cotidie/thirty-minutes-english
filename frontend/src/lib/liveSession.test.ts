import { describe, expect, it } from 'vitest'
import { applyLiveEvent, initialLiveState, liveFailed } from './liveSession'

describe('applyLiveEvent', () => {
  it('moves to listening with the session id on session.started', () => {
    const s = applyLiveEvent(initialLiveState, { type: 'session.started', session: { id: 'live_1' } })
    expect(s.status).toBe('listening')
    expect(s.sessionId).toBe('live_1')
  })

  it('appends transcript deltas verbatim per speaker', () => {
    let s = initialLiveState
    s = applyLiveEvent(s, { type: 'session.input_transcript.delta', delta: 'Researchers ' })
    s = applyLiveEvent(s, { type: 'session.output_transcript.delta', delta: 'Quick one:' })
    s = applyLiveEvent(s, { type: 'session.input_transcript.delta', delta: 'berified' })
    s = applyLiveEvent(s, { type: 'session.output_transcript.delta', delta: ' verify.' })
    expect(s.reader).toBe('Researchers berified')
    expect(s.coach).toBe('Quick one: verify.')
  })

  it('takes usage as a snapshot, not a sum', () => {
    let s = applyLiveEvent(initialLiveState, { type: 'session.usage.updated', usage: { seconds: 12 } })
    s = applyLiveEvent(s, { type: 'session.usage.updated', usage: { seconds: 20 } })
    expect(s.seconds).toBe(20)
  })

  it('closes with the final seconds and keeps transcripts', () => {
    let s = applyLiveEvent(initialLiveState, { type: 'session.output_transcript.delta', delta: 'Nice work.' })
    s = applyLiveEvent(s, { type: 'session.closed', usage: { seconds: 95 }, reason: 'close_requested' })
    expect(s.status).toBe('closed')
    expect(s.seconds).toBe(95)
    expect(s.coach).toBe('Nice work.')
  })

  it('records an error message without ending the session', () => {
    const s = applyLiveEvent(
      applyLiveEvent(initialLiveState, { type: 'session.started' }),
      { type: 'error', error: { message: 'moderation cut audio' } },
    )
    expect(s.status).toBe('listening')
    expect(s.error).toBe('moderation cut audio')
  })

  it('ignores unknown events and marks a transport failure', () => {
    const s = applyLiveEvent(initialLiveState, { type: 'session.delegation.created' })
    expect(s).toEqual(initialLiveState)
    expect(liveFailed(s, 'mic denied')).toMatchObject({ status: 'failed', error: 'mic denied' })
  })
})
