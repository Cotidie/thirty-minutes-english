import { describe, expect, it } from 'vitest'
import { audioChunk, decodeServerMessage, fromBase64, textTurn, toBase64 } from './geminiEvents'

describe('decodeServerMessage', () => {
  it('turns setupComplete into session.started', () => {
    expect(decodeServerMessage({ setupComplete: {} }).events).toEqual([{ type: 'session.started' }])
  })

  it('maps both transcripts onto the delta events the app already knows', () => {
    const decoded = decodeServerMessage({
      serverContent: { inputTranscription: { text: 'I read ' }, outputTranscription: { text: 'Stop. ' } },
    })
    expect(decoded.events).toEqual([
      { type: 'session.input_transcript.delta', delta: 'I read ' },
      { type: 'session.output_transcript.delta', delta: 'Stop. ' },
    ])
  })

  it('drops the silent-turn and noise markers Gemini puts in transcripts', () => {
    const silent = decodeServerMessage({ serverContent: { outputTranscription: { text: '<no speech>' } } })
    expect(silent.events).toEqual([])
    const mixed = decodeServerMessage({
      serverContent: { inputTranscription: { text: '<noise>the courtroom.' }, outputTranscription: { text: '<no speech>Goodbye.' } },
    })
    expect(mixed.events).toEqual([
      { type: 'session.input_transcript.delta', delta: 'the courtroom.' },
      { type: 'session.output_transcript.delta', delta: 'Goodbye.' },
    ])
  })

  it('collects pcm audio parts in order and skips other parts', () => {
    const decoded = decodeServerMessage({
      serverContent: {
        modelTurn: {
          parts: [
            { inlineData: { mimeType: 'audio/pcm;rate=24000', data: 'AAA=' } },
            { text: 'thought' },
            { inlineData: { mimeType: 'audio/pcm;rate=24000', data: 'AQE=' } },
          ],
        },
      },
    })
    expect(decoded.audio).toEqual(['AAA=', 'AQE='])
    expect(decoded.events).toEqual([])
  })

  it('flags interruption, turn completion, and goAway', () => {
    expect(decodeServerMessage({ serverContent: { interrupted: true } }).interrupted).toBe(true)
    expect(decodeServerMessage({ serverContent: { turnComplete: true } }).turnComplete).toBe(true)
    expect(decodeServerMessage({ goAway: { timeLeft: '10s' } }).goAway).toBe(true)
    expect(decodeServerMessage({}).interrupted).toBe(false)
  })

  it('surfaces an error message', () => {
    expect(decodeServerMessage({ error: { message: 'quota' } }).events).toEqual([
      { type: 'error', error: { message: 'quota' } },
    ])
  })
})

describe('client messages', () => {
  it('sends text as a complete user turn', () => {
    expect(textTurn('Say hi')).toEqual({
      clientContent: { turns: [{ role: 'user', parts: [{ text: 'Say hi' }] }], turnComplete: true },
    })
  })

  it('tags audio chunks with the 16 kHz pcm mime type', () => {
    expect(audioChunk('AAA=')).toEqual({ realtimeInput: { audio: { data: 'AAA=', mimeType: 'audio/pcm;rate=16000' } } })
  })

  it('round-trips bytes through base64', () => {
    const bytes = new Int16Array([0, 1, -1, 32767, -32768]).buffer
    expect(new Int16Array(fromBase64(toBase64(bytes)))).toEqual(new Int16Array(bytes))
  })
})
