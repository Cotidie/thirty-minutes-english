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

export interface Article {
  title: string
  body: string
  questions: Question[]
  sources?: Source[]
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

export interface TopicListing {
  topics: Topic[]
  /** Today's news half has not landed yet; the list is pool topics for now. */
  pending: boolean
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

export interface Ask {
  id: number
  created_at: string
  session_id: number | null
  user_text: string
  coach_text: string
  seconds: number
  card: PhraseCard | null
}
