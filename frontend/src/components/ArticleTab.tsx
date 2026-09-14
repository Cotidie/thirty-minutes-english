import { useEffect, useRef, useState } from 'react'
import { highlightSegments } from '../lib/highlight'
import type { Article, Question } from '../types'
import { ReadAloud } from './ReadAloud'

export function ArticleTab({ article, sessionId }: { article: Article; sessionId: number | null }) {
  const [active, setActive] = useState<number | null>(null)
  const [reading, setReading] = useState<number | null>(null)
  const bodyRef = useRef<HTMLElement>(null)
  const paragraphs = article.body.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
  const evidence = active === null ? [] : article.questions[active].evidence

  useEffect(() => {
    bodyRef.current?.querySelector('mark')?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }, [active])

  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read silently for three minutes. Then each of you summarizes the article in your own words before opening the
        questions. Click a question to see the passage it comes from. Press Read aloud under a paragraph to have a
        native-speaker coach listen and correct your pronunciation as you read it.
      </p>
      <article className="article" ref={bodyRef}>
        <h2 className="article-title">{article.title}</h2>
        {paragraphs.map((p, i) => (
          <div key={i} className="paragraph">
            <p>
              {highlightSegments(p, evidence).map((seg, j) =>
                seg.marked ? <mark key={j}>{seg.text}</mark> : <span key={j}>{seg.text}</span>,
              )}
            </p>
            <ReadAloud
              paragraph={p}
              sessionId={sessionId}
              active={reading !== null && reading !== i}
              onStart={() => setReading(i)}
              onEnd={() => setReading(null)}
            />
          </div>
        ))}
      </article>
      <details className="questions" open={active !== null || undefined}>
        <summary>Discussion questions</summary>
        <ol>
          {article.questions.map((q, i) => (
            <li key={q.text}>
              <QuestionItem question={q} active={active === i} onToggle={() => setActive(active === i ? null : i)} />
            </li>
          ))}
        </ol>
      </details>
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
  if (question.evidence.length === 0) return <span className="question">{question.text}</span>
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
