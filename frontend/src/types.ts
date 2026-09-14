export interface Expression {
  phrase: string
  meaning: string
  usage_note: string
  examples: string[]
}

export interface Question {
  text: string
  evidence: string[]
}

export interface Source {
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
}

export interface SessionContent {
  topic: string
  expressions: Expression[]
  article: Article
  vocabulary: VocabularyItem[]
}

export type Category = 'tech' | 'literature' | 'history' | 'world' | 'news'

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

export interface LiveSession {
  session: { id: string }
  transport: { type: 'webrtc'; sdp: string }
}

export interface PhraseCard {
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
}

export function practiceExpression(e: Expression): PracticeTarget {
  return { text: e.phrase, meaning: e.meaning, note: e.usage_note }
}

export function practiceWord(v: VocabularyItem): PracticeTarget {
  return { text: v.word, meaning: v.definition, note: `part of speech: ${v.pos}` }
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
  feedback: string
}
