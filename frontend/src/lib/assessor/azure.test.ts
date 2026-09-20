import { beforeEach, describe, expect, it, vi } from 'vitest'

const recognizers: FakeRecognizer[] = []
const applied: { json: string; prosody: boolean }[] = []
const properties: Record<string, string> = {}

class FakeRecognizer {
  recognized: ((s: unknown, e: unknown) => void) | null = null
  canceled: ((s: unknown, e: unknown) => void) | null = null
  started = false
  stopped = false
  closed = false
  speechConfig: unknown
  audioConfig: unknown
  constructor(speechConfig: unknown, audioConfig: unknown) {
    this.speechConfig = speechConfig
    this.audioConfig = audioConfig
    recognizers.push(this)
  }
  startContinuousRecognitionAsync(ok: () => void) {
    this.started = true
    ok()
  }
  stopContinuousRecognitionAsync(ok: () => void) {
    this.stopped = true
    ok()
  }
  close() {
    this.closed = true
  }
}

vi.mock('microsoft-cognitiveservices-speech-sdk', () => ({
  SpeechConfig: {
    fromAuthorizationToken: vi.fn((token: string, region: string) => ({
      token,
      region,
      speechRecognitionLanguage: '',
      setProperty: (k: string, v: string) => {
        properties[k] = v
      },
    })),
  },
  AudioConfig: { fromStreamInput: vi.fn((stream: MediaStream) => ({ stream })) },
  PronunciationAssessmentConfig: {
    fromJSON: vi.fn((json: string) => {
      const cfg = {
        enableProsodyAssessment: false,
        applyTo: vi.fn(() => applied.push({ json, prosody: cfg.enableProsodyAssessment })),
      }
      return cfg
    }),
  },
  SpeechRecognizer: FakeRecognizer,
  PropertyId: { SpeechServiceResponse_JsonResult: 'json', Speech_SegmentationSilenceTimeoutMs: 'segmentation' },
  ResultReason: { RecognizedSpeech: 3 },
}))

import { startAzureAssessor } from './azure'

const session = { token: 'eyJ.t', region: 'koreacentral', word_score: 60, break_confidence: 0.75 }

beforeEach(() => {
  recognizers.length = 0
  applied.length = 0
})

describe('startAzureAssessor', () => {
  it('streams the microphone with the paragraph as reference text and reports each segment', async () => {
    const onSegment = vi.fn()
    const mic = {} as MediaStream
    const assessor = await startAzureAssessor({ microphone: mic, paragraph: 'Researchers verified it.', session, onSegment, onError: vi.fn() })

    const reco = recognizers[0]
    expect(reco.started).toBe(true)
    expect((reco.audioConfig as { stream: MediaStream }).stream).toBe(mic)
    expect((reco.speechConfig as { speechRecognitionLanguage: string }).speechRecognitionLanguage).toBe('en-US')
    expect(properties.segmentation).toBe('400')
    expect(JSON.parse(applied[0].json)).toMatchObject({
      referenceText: 'Researchers verified it.',
      granularity: 'Phoneme',
      phonemeAlphabet: 'IPA',
      nBestPhonemeCount: 5,
      enableMiscue: false,
    })
    expect(applied[0].prosody).toBe(true)

    const words = [{ Word: 'researchers', Offset: 0, Duration: 1, PronunciationAssessment: { AccuracyScore: 90, ErrorType: 'None' } }]
    reco.recognized?.(null, { result: { reason: 3, properties: { getProperty: () => JSON.stringify({ NBest: [{ Words: words }] }) } } })
    expect(onSegment).toHaveBeenCalledWith(words)

    await assessor.stop()
    expect(reco.stopped).toBe(true)
    expect(reco.closed).toBe(true)
  })

  it('reports a cancellation as an error', async () => {
    const onError = vi.fn()
    await startAzureAssessor({ microphone: {} as MediaStream, paragraph: 'x', session, onSegment: vi.fn(), onError })
    recognizers[0].canceled?.(null, { errorDetails: 'WebSocket upgrade failed: 401' })
    expect(onError).toHaveBeenCalledWith('WebSocket upgrade failed: 401')
  })
})
