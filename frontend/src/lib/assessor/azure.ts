// Azure Pronunciation Assessment on the round's microphone. The SDK does the
// streaming; we hand it the MediaStream, the paragraph as reference text, and
// pass every recognised segment's word list and text to the caller. The SDK is a megabyte, so it loads on first use only.

import type { AssessorSession } from '../../types'
import type { AzureWord } from './judge'

const LOCALE = 'en-US'
/** Silence that ends a segment. Short, so findings arrive at phrase pauses. */
const SEGMENT_SILENCE_MS = '400'

export interface AssessorOptions {
  microphone: MediaStream
  paragraph: string
  session: AssessorSession
  onSegment: (words: AzureWord[], text: string) => void
  onError: (message: string) => void
}

export interface Assessor {
  stop(): Promise<void>
}

export async function startAzureAssessor(opts: AssessorOptions): Promise<Assessor> {
  const sdk = await import('microsoft-cognitiveservices-speech-sdk')

  const speech = sdk.SpeechConfig.fromAuthorizationToken(opts.session.token, opts.session.region)
  speech.speechRecognitionLanguage = LOCALE
  speech.setProperty(sdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, SEGMENT_SILENCE_MS)

  const recognizer = new sdk.SpeechRecognizer(speech, sdk.AudioConfig.fromStreamInput(opts.microphone))
  const assessment = sdk.PronunciationAssessmentConfig.fromJSON(
    JSON.stringify({
      referenceText: opts.paragraph,
      gradingSystem: 'HundredMark',
      granularity: 'Phoneme',
      phonemeAlphabet: 'IPA',
      nBestPhonemeCount: 5,
      enableMiscue: false,
    }),
  )
  assessment.enableProsodyAssessment = true
  assessment.applyTo(recognizer)

  recognizer.recognized = (_, e) => {
    if (e.result.reason !== sdk.ResultReason.RecognizedSpeech) return
    const raw = e.result.properties.getProperty(sdk.PropertyId.SpeechServiceResponse_JsonResult)
    const json = JSON.parse(raw) as { NBest?: { Words?: AzureWord[] }[] }
    opts.onSegment(json.NBest?.[0]?.Words ?? [], e.result.text)
  }
  recognizer.canceled = (_, e) => {
    if (e.errorDetails) opts.onError(e.errorDetails)
  }

  await new Promise<void>((resolve, reject) =>
    recognizer.startContinuousRecognitionAsync(resolve, (err) => reject(new Error(err))),
  )

  return {
    stop: () =>
      new Promise<void>((resolve) => {
        const done = () => {
          recognizer.close()
          resolve()
        }
        recognizer.stopContinuousRecognitionAsync(done, done)
      }),
  }
}
