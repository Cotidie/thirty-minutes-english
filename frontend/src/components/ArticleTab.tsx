import { useEffect, useRef, useState } from 'react'
import { markedSpans, segmentsIn } from '../lib/highlight'
import { pairSentences } from '../lib/sentences'
import type { Article, Question } from '../types'
import { ReadAloud } from './ReadAloud'
import { Run, Sentence } from './Sentence'

export function ArticleTab({ article, sessionId }: { article: Article; sessionId: number | null }) {
  const [active, setActive] = useState<number | null>(null)
  const [reading, setReading] = useState<number | null>(null)
  /** Paragraphs still showing their read-aloud marks after the round. */
  const [marked, setMarked] = useState<Set<number>>(new Set())
  const bodyRef = useRef<HTMLElement>(null)
  const paragraphs = article.body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
  const sentences = pairSentences(paragraphs, article.translation ?? [])
  const evidence = active === null ? [] : article.questions[active].evidence

  useEffect(() => {
    bodyRef.current?.querySelector('mark')?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }, [active])

  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read it, then each of you sums it up in your own words before the questions. Click a sentence for the Korean, a
        question for its passage.
      </p>
      <article className="article" ref={bodyRef}>
        <h2 className="article-title">{article.title}</h2>
        {paragraphs.map((p, i) => {
          const spans = markedSpans(p, evidence)
          return (
            <div key={i} className="paragraph">
              <p hidden={reading === i || marked.has(i)}>
                {sentences[i].map((piece, j) => {
                  const segments = segmentsIn(piece.text, spans, piece.start)
                  return piece.ko === null ? (
                    <Run key={j} segments={segments} />
                  ) : (
                    <Sentence key={j} segments={segments} ko={piece.ko} />
                  )
                })}
              </p>
              <ReadAloud
                paragraph={p}
                sessionId={sessionId}
                active={reading !== null && reading !== i}
                onStart={() => setReading(i)}
                onEnd={(kept) => {
                  setReading(null)
                  setMarked((m) => {
                    const next = new Set(m)
                    if (kept) next.add(i)
                    else next.delete(i)
                    return next
                  })
                }}
              />
            </div>
          )
        })}
      </article>
      <section className="questions">
        <h3>Discussion questions</h3>
        <ol>
          {article.questions.map((q, i) => (
            <li key={q.text}>
              <QuestionItem question={q} active={active === i} onToggle={() => setActive(active === i ? null : i)} />
            </li>
          ))}
        </ol>
      </section>
      {article.sources && article.sources.length > 0 && (
        <details className="sources">
          <summary>Sources</summary>
          <ul>
            {article.sources.map((src) => (
              <li key={src.url}>
                <a href={src.url} target="_blank" rel="noreferrer">
                  {src.title}
                </a>
                <span className="source-host">{hostOf(src.url)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function QuestionItem({ question, active, onToggle }: { question: Question; active: boolean; onToggle: () => void }) {
  // Nothing in the article answers it, so there is no passage to point at.
  if (question.evidence.length === 0) {
    return (
      <span className="question is-open">
        {question.text}
        <span className="question-tag">your take</span>
      </span>
    )
  }
  return (
    <button type="button" className={`question${active ? ' is-active' : ''}`} aria-pressed={active} onClick={onToggle}>
      {question.text}
    </button>
  )
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}
