import type { Shown } from './lib/assessor/judge'

/** One expression of the corpus; stars and sentences point at it by id. */
export interface Expression {
  id: number
  phrase: string
  meaning: string
  /** Plainer words for the same meaning; absent on older sessions. */
  synonyms?: string[]
  usage_note: string
  examples: string[]
  /** The Korean equivalent, hidden behind a chip until tapped. */
  korean?: string | null
}

export interface Question {
  text: string
  evidence: string[]
}

interface Source {
  title: string
  url: string
}

/** One sentence of the body, copied exactly, and its Korean. */
export interface SentencePair {
  en: string
  ko: string
}

/** One paragraph of the article; readings and summaries point at it by id. */
export interface Paragraph {
  id: number
  text: string
}

export interface Article {
  title: string
  paragraphs: Paragraph[]
  questions: Question[]
  sources?: Source[]
  translation?: SentencePair[]
}

/** One word of the session; stars and sentences point at it by id. */
export interface VocabularyItem {
  id: number
  word: string
  pos: string
  definition: string
  /** Plainer words for the same sense, shown with the definition. */
  synonyms?: string[]
  example: string
  /** The Korean equivalent, hidden on the card until tapped. */
  korean?: string | null
  /** A situation the word fits, drawn for the card; the learner describes it with the word. */
  scene?: string | null
  /** One or two sentences on what the picture shows and why it is the word; hidden until asked for. */
  caption?: string | null
  /** The scene drawn, for Practice: a file name under /api/images/. */
  image?: string | null
  /** The example sentence drawn; the picture the card opens on. */
  example_image?: string | null
}

/** A word has two pictures: its example sentence, and the scene to describe in Practice. */
export type PictureFace = 'example' | 'practice'


export interface SessionContent {
  topic: string
  expressions: Expression[]
  article: Article
  vocabulary: VocabularyItem[]
}

export interface Topic {
  text: string
  /** A category id; its name comes with the listing's `labels`. */
  category: string
}

export interface Note {
  text: string
}

/** What the pair starred in a session: expression ids and word ids. */
export interface Stars {
  expressions: number[]
  words: number[]
}

export interface TopicListing {
  topics: Topic[]
  /** Today's news half has not landed yet; the list is pool topics for now. */
  pending: boolean
  /** Why the last news fetch brought nothing, or null once one succeeds. */
  error: string | null
  /** Every category's name, in the order the key lists them. */
  labels: Record<string, string>
}

export interface SessionSummary {
  id: number
  created_at: string
  topic: string
  title: string
}

export interface Session {
  id: number
  created_at: string
  topic: string
  content: SessionContent
}

/** OpenAI answers the browser's WebRTC offer. */
interface OpenAILiveSession {
  provider: 'openai'
  session: { id: string }
  transport: { type: 'webrtc'; sdp: string }
}

/** Gemini hands out a one-use token in the socket URL and the setup message to send first. */
interface GeminiLiveSession {
  provider: 'gemini'
  url: string
  setup: Record<string, unknown>
}

export type LiveSession = OpenAILiveSession | GeminiLiveSession
export type VoiceProvider = LiveSession['provider']

/** One runtime setting, its effective value; secrets come masked. */
/** One menu entry: a model, a provider, a style, a skill. */
export interface SettingOption {
  id: string
  label: string
  description: string
  /** A Claude model's effort levels; [] = it takes none; null = not a Claude model. */
  efforts: string[] | null
  /** Image models: list price in dollars per million image-output / prompt tokens. */
  image_per_m?: number | null
  text_per_m?: number | null
  /** Image models: what a picture cost here on average, over its latest pictures. */
  per_image?: number | null
  /** Image models: how long a picture took here on average. */
  seconds_per_image?: number | null
  /** Kept at the top of the menu however old it gets. */
  pinned?: boolean
}

interface SettingVariant {
  default: string
  /** The model list behind `options`; pins are kept per list. */
  catalog: string
  options: SettingOption[]
}

export interface SettingField {
  key: string
  group: string
  value: string
  secret: boolean
  default: string
  /** The menu. Strict unless `free`. */
  options: SettingOption[]
  /** Any text is allowed; `options` only suggest (model ids). */
  free: boolean
  /** The model list behind `options`; pins are kept per list. */
  catalog: string | null
  /** Draw the model menu as a list in the panel, with prices, not a dropdown. */
  inline: boolean
  /** A Test button can check this key. */
  testable: boolean
  /** The setting whose current value picks one of `variants` (its default and menu). */
  follows: string | null
  variants: Record<string, SettingVariant>
  /** An effort level: the menu is what the model in that field takes. */
  effort_of: string | null
  /** [key, value]: the field only shows while that setting holds that value. */
  shown_when: [string, string] | null
  /** [key, value]: a key the app only calls while that setting holds that value. */
  used_when: [string, string] | null
  /** What the setting does, for the info tooltip. */
  help: string
  /** `options` are ticked, not picked; the value is a comma list. */
  multi: boolean
}

export interface SettingGroup {
  id: string
  title: string
}

/** What the redraw menu shows: style keys with their labels, and the one Settings holds. */
export interface PictureStyles {
  current: string
  options: SettingOption[]
}

export interface SettingsView {
  groups: SettingGroup[]
  fields: SettingField[]
}

export type SettingsUpdate = Record<string, string>

export interface KeyTestResult {
  ok: boolean
  message: string
}

/** A ten-minute Azure token plus the score the round judges with. */
export interface AssessorSession {
  token: string
  region: string
  word_score: number
}

/** A mark as a reading keeps it, so it can go back on the paragraph. Readings kept before
 * the marks were saved have `at` -1 and no sounds. */
export type Correction = Shown

export interface Reading {
  id: number
  created_at: string
  paragraph_id: number
  user_text: string
  seconds: number
  corrections: Correction[] | null
}

/** What a Practice round is about: an expression or a word, with what the coach needs to judge a sentence. */
export interface PracticeTarget {
  /** The expression's id or the word's, as `kind` says. */
  id: number
  text: string
  meaning: string
  note: string
  /** An expression gets the light native fix; a word gets a free rewording that uses it well. */
  kind: 'expression' | 'word'
  /** For a word: what its picture shows. */
  scene?: string
}

export function practiceExpression(e: Expression): PracticeTarget {
  return { id: e.id, text: e.phrase, meaning: e.meaning, note: e.usage_note, kind: 'expression' }
}

export function practiceWord(v: VocabularyItem): PracticeTarget {
  return { id: v.id, text: v.word, meaning: v.definition, note: `part of speech: ${v.pos}`, kind: 'word', scene: v.scene ?? undefined }
}

/** One weakness in how the reader said it: their words and the better ones. */
export interface SummaryFix {
  said: string
  better: string
}

/** A spoken summary judged against its paragraph, in a shape read at a glance. */
export interface SummaryFeedback {
  /** The one key point left out or got wrong, or none. */
  missed: string[]
  /** Two at most. */
  fixes: SummaryFix[]
  /** The model answer: what the reader said, in one or two short sentences. */
  summary: string
}

/** One paragraph summed up out loud, and what the coach made of it. */
export interface Summary {
  id: number
  created_at: string
  paragraph_id: number
  user_text: string
  feedback: SummaryFeedback
  seconds: number
}

/** One sentence made with an expression or a word (exactly one of the two ids), and the coach's echo of it. */
export interface Example {
  id: number
  created_at: string
  expression_id: number | null
  vocabulary_id: number | null
  user_text: string
  coach_text: string
  seconds: number
}

/** A sentence said back the native way, and one line on the change that matters most. */
export interface ExampleFeedback {
  paraphrase: string
  /** One short sentence per change, most important first. */
  feedback: string[]
}
