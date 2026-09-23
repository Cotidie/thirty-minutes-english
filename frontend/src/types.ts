export interface Expression {
  phrase: string
  meaning: string
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

export interface Article {
  title: string
  body: string
  questions: Question[]
  sources?: Source[]
  translation?: SentencePair[]
}

export interface VocabularyItem {
  word: string
  pos: string
  definition: string
  example: string
  /** The Korean equivalent, hidden on the card until tapped. */
  korean?: string | null
  /** A situation the word fits, drawn for the card; the learner describes it with the word. */
  scene?: string | null
  /** File name under /api/images/. */
  image?: string | null
}

export interface SessionContent {
  topic: string
  expressions: Expression[]
  article: Article
  vocabulary: VocabularyItem[]
}

export type Category = 'cs' | 'ie' | 'ai' | 'literature' | 'history' | 'world' | 'korea' | 'research' | 'news'

export interface Topic {
  text: string
  category: Category
}

/** Phrases and words starred in a session. */
export interface Stars {
  expressions: string[]
  words: string[]
}

export interface TopicListing {
  topics: Topic[]
  /** Today's news half has not landed yet; the list is pool topics for now. */
  pending: boolean
  /** Why the last news fetch brought nothing, or null once one succeeds. */
  error: string | null
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

export type SettingGroup = 'keys' | 'voice' | 'assess' | 'claude' | 'text' | 'images'

/** One runtime setting, its effective value; secrets come masked. */
export interface SettingField {
  key: string
  group: SettingGroup
  value: string
  secret: boolean
  default: string
  /** Strict list: the backend rejects anything else. */
  choices: string[] | null
  /** Free text with a menu of common values. */
  suggestions: string[]
  /** A short description per choice, shown in the menu. */
  labels: Record<string, string>
}

/** What the redraw menu shows: style keys with their labels, and the one Settings holds. */
export interface PictureStyles {
  current: string
  choices: string[]
  labels: Record<string, string>
}

export interface SettingsView {
  fields: SettingField[]
}

export type SettingsUpdate = Record<string, string>

export type ApiKeyName =
  | 'OPENAI_API_KEY'
  | 'GEMINI_API_KEY'
  | 'AZURE_SPEECH_KEY'
  | 'OPENROUTER_API_KEY'
  | 'COMFY_API_KEY'
  | 'FIRECRAWL_API_KEY'

export interface KeyTestResult {
  ok: boolean
  message: string
}

/** A ten-minute Azure token plus how the round judges with it. */
export interface AssessorSession {
  token: string
  region: string
  word_score: number
  break_confidence: number
}

interface PhraseCard {
  asked: string
  english: string
  alternatives: string[]
  note: string
}

export interface Correction {
  kind: 'pronunciation' | 'phrasing'
  word: string
  heard: string
  fix: string
  repeated_ok: boolean
}

export interface Reading {
  id: number
  created_at: string
  session_id: number | null
  paragraph: string
  user_text: string
  coach_text: string
  seconds: number
  corrections: Correction[] | null
}

/** What a Practice round is about: an expression or a word, with what the coach needs to judge a sentence. */
export interface PracticeTarget {
  text: string
  meaning: string
  note: string
  /** An expression gets the light native fix; a word gets a free rewording that uses it well. */
  kind: 'expression' | 'word'
  /** For a word: what its picture shows. */
  scene?: string
}

export function practiceExpression(e: Expression): PracticeTarget {
  return { text: e.phrase, meaning: e.meaning, note: e.usage_note, kind: 'expression' }
}

export function practiceWord(v: VocabularyItem): PracticeTarget {
  return { text: v.word, meaning: v.definition, note: `part of speech: ${v.pos}`, kind: 'word', scene: v.scene ?? undefined }
}

/** One sentence made with an expression or word, and the coach's echo of it. */
export interface Example {
  id: number
  created_at: string
  session_id: number
  expression: string
  user_text: string
  coach_text: string
  seconds: number
}

export interface Ask {
  id: number
  created_at: string
  session_id: number | null
  user_text: string
  coach_text: string
  seconds: number
  card: PhraseCard | null
}

/** A sentence said back the native way, and one line on the change that matters most. */
export interface ExampleFeedback {
  paraphrase: string
  /** One short sentence per change, most important first. */
  feedback: string[]
}
