export interface Expression {
  phrase: string
  meaning: string
  usage_note: string
  examples: string[]
}

export interface Article {
  title: string
  body: string
  questions: string[]
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
