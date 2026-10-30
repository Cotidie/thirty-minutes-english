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
  /** Said in English by each of the pair, then tapped for the model answer; null until the corpus has one. */
  korean_example?: KoreanExample | null
}

export interface KoreanExample {
  korean: string
  /** The model answer: one way to say `korean` with the expression. */
  english: string
}

/** An expression as the corpus keeps it, for the corpus page. */
export interface CorpusEntry extends Expression {
  /** casual, workplace or discussion; null when the source did not say. */
  setting: string | null
  /** The post it was read from. */
  source: string
  added_at: string
  /** Ids of the sessions that taught it, oldest first. */
  sessions: number[]
  /** Ids of the sessions it was swapped out of, oldest first; those count as using it too. */
  swapped: number[]
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

/** An image under a paragraph, or under the title as the cover (no paragraph): from a page the article drew on
 * (with its page and credit), or drawn for it (neither). */
export interface Figure {
  id: number
  paragraph_id: number | null
  /** A file name under /api/images/. */
  image: string
  caption: string
  source_url: string | null
  credit: string | null
}

export interface Article {
  title: string
  paragraphs: Paragraph[]
  /** Absent on sessions made before figures were kept. */
  figures?: Figure[]
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

/** A topic as the database keeps it, for the database page. */
export interface TopicEntry extends Topic {
  id: number
  added_at: string
  /** Days it was among the day's news, oldest first. */
  news_days: string[]
  /** Ids of the sessions written on it, oldest first. */
  sessions: number[]
}

/** Every topic, with every category's name (typed-in ones too). */
export interface TopicLibrary {
  topics: TopicEntry[]
  labels: Record<string, string>
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

/** The logged-in account. */
export interface Me {
  id: number
  email: string
  is_admin: boolean
  can_create: boolean
}

/** An account as the admin sees it. */
export interface Account extends Me {
  created_at: string
}

/** Someone a session is shared with. */
export interface ShareEntry {
  user_id: number
  email: string
}

export interface SessionSummary {
  id: number
  created_at: string
  topic: string
  title: string
  /** Whether this account made it; if not, `shared_by` is who did. */
  mine: boolean
  shared_by: string | null
}

export interface Session {
  id: number
  created_at: string
  topic: string
  content: SessionContent
  /** Whether this account made it; if not, `shared_by` is who did. */
  mine: boolean
  shared_by: string | null
}

/** A Gemini Live round: a one-use token in the socket URL and the setup message to send first. */
export interface LiveSession {
  url: string
  setup: Record<string, unknown>
}

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
  /** An effort level: the menu is what the model in that field takes. */
  effort_of: string | null
  /** [key, value]: the field only shows while that setting holds that value. */
  shown_when: [string, string] | null
  /** [key, value]: a key the app only calls while that setting holds that value. */
  used_when: [string, string] | null
  /** What the setting does, for the info tooltip. */
  help: string
}

export interface SettingGroup {
  id: string
  title: string
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
/** The word a Practice round is about: the coach rewords the sentence freely so it uses the word well. */
export interface PracticeTarget {
  /** The word's vocabulary id. */
  id: number
  word: string
  meaning: string
  /** Its part of speech. */
  pos: string
  /** What its picture shows. */
  scene?: string
}

export function practiceWord(v: VocabularyItem): PracticeTarget {
  return { id: v.id, word: v.word, meaning: v.definition, pos: v.pos, scene: v.scene ?? undefined }
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

/** One sentence made with one of the session's words, and the coach's echo of it. */
export interface Example {
  id: number
  created_at: string
  vocabulary_id: number
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
