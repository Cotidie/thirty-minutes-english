import { useState } from 'react'
import { useSharedView } from '../lib/presence/useSharedView'
import type { Expression, KoreanExample, KoreanLine } from '../types'
import { StarButton } from './StarButton'
import { KoreanChip } from './KoreanChip'
import { Synonyms } from './Synonyms'
import { Marked } from './Marked'
import './ExpressionsTab.css'

interface Props {
  items: Expression[]
  /** Ids of the starred expressions. */
  starred: number[]
  onToggleStar: (id: number) => void
  /** Puts another corpus expression in this one's place; rejects with what went wrong. */
  onSwap: (id: number) => Promise<void>
  /** Teaches one more corpus expression after the others; rejects with what went wrong. */
  onAdd: () => Promise<void>
}

/** What a failed change was about: an expression's swap, or the add. */
type Failure = { at: number | 'add'; message: string }

export function ExpressionsTab({ items, starred, onToggleStar, onSwap, onAdd }: Props) {
  // One change at a time, so two at once cannot pick the same expression.
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)

  async function change(at: Failure['at'], run: () => Promise<void>) {
    setBusy(true)
    setFailure(null)
    try {
      await run()
    } catch (e) {
      setFailure({ at, message: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const add = (
    <>
      <button
        type="button"
        className="expression-add"
        aria-label="Add another expression"
        title="Add another expression"
        disabled={busy}
        onClick={() => void change('add', onAdd)}
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
          <path d="M10 4v12M4 10h12" />
        </svg>
      </button>
      {failure?.at === 'add' && <p className="error">Could not add one: {failure.message}</p>}
    </>
  )

  if (items.length === 0) {
    return (
      <section className="tab-panel">
        <p className="empty">This session has no expressions.</p>
        {add}
      </section>
    )
  }
  return (
    <section className="tab-panel">
      <p className="tab-brief" data-presence-anchor="brief">
        Read the examples aloud, then say the Korean in English, each of you a sentence or one side of the dialogue,
        before you tap it for the model answer.
      </p>
      <ol className="expression-list">
        {items.map((item) => (
          <li key={item.id} className="expression" data-presence-anchor={`expression:${item.id}`}>
            <div className="expression-head">
              <h3 className="expression-phrase">{item.phrase}</h3>
              {item.korean && <KoreanChip korean={item.korean} of={item.phrase} viewKey={`chip:expression:${item.id}`} />}
              <button
                type="button"
                className="expression-swap"
                aria-label={`Swap ${item.phrase} for another expression`}
                title="Swap for another expression"
                disabled={busy}
                onClick={() => void change(item.id, () => onSwap(item.id))}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M13.5 8a5.5 5.5 0 0 1-9.7 3.6M2.5 8a5.5 5.5 0 0 1 9.7-3.6" />
                  <path d="M12.6 1.6v2.8H9.8M3.4 14.4v-2.8h2.8" />
                </svg>
              </button>
              <StarButton
                label={item.phrase}
                on={starred.includes(item.id)}
                onToggle={() => onToggleStar(item.id)}
              />
            </div>
            {failure?.at === item.id && <p className="error">Could not swap it: {failure.message}</p>}
            <p className="expression-meaning">
              {item.meaning}
              <Synonyms words={item.synonyms} />
            </p>
            <p className="expression-note">{item.usage_note}</p>
            <ul className="expression-examples">
              {item.examples.map((ex) => (
                <li key={ex}>
                  <Marked text={ex} word={item.phrase} />
                </li>
              ))}
            </ul>
            {(item.korean_example || item.korean_dialogue) && <KoreanPractice expression={item} />}
          </li>
        ))}
      </ol>
      {add}
    </section>
  )
}

type Mode = 'dialogue' | 'solo'

const KOREAN_HINT = '영어로 어떻게 말할까요?'
const ENGLISH_HINT = '모범 답안 · 다르게 말해도 표현을 넣었으면 충분해요'

/** Korean to say in English: the one sentence, the two-line dialogue, or a toggle between them when the expression has
 * both. The mode is shared with everyone in the session, like what is turned over. */
function KoreanPractice({ expression }: { expression: Expression }) {
  const { id, phrase, korean_example: example, korean_dialogue: dialogue } = expression
  const [chosen, setMode] = useSharedView<Mode>(`mode:${id}`, 'dialogue')
  const mode: Mode = !dialogue ? 'solo' : !example ? 'dialogue' : chosen
  return (
    <div className="korean-example">
      <div className="korean-example-head">
        <p className="korean-example-label">한국어로 해 보기</p>
        {example && dialogue && <ModeToggle mode={mode} onChange={setMode} />}
      </div>
      {mode === 'dialogue' && dialogue ? (
        <KoreanDialogue expressionId={id} lines={dialogue} phrase={phrase} />
      ) : (
        example && <KoreanSentence expressionId={id} example={example} phrase={phrase} />
      )}
    </div>
  )
}

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  const choices: [Mode, string][] = [
    ['solo', '한 문장'],
    ['dialogue', '대화'],
  ]
  return (
    <div className="korean-practice-modes" role="group" aria-label="연습 방식">
      {choices.map(([value, label]) => (
        <button key={value} type="button" aria-pressed={mode === value} onClick={() => onChange(value)}>
          {label}
        </button>
      ))}
    </div>
  )
}

/** The Korean sentence until tapped, then the English model answer with the expression marked. */
function KoreanSentence({ expressionId, example, phrase }: { expressionId: number; example: KoreanExample; phrase: string }) {
  const [english, setEnglish] = useSharedView<boolean>(`example:${expressionId}`, false)
  return (
    <button type="button" className="korean-example-card" aria-pressed={english} onClick={() => setEnglish(!english)}>
      {english ? (
        <span className="korean-example-english">
          <Marked text={example.english} word={phrase} />
        </span>
      ) : (
        <span className="korean-example-korean" lang="ko">
          {example.korean}
        </span>
      )}
      <span className="korean-example-hint">{english ? ENGLISH_HINT : KOREAN_HINT}</span>
    </button>
  )
}

/** A's and B's lines in Korean until tapped, then both English model answers, the expression marked where it is used. */
function KoreanDialogue({ expressionId, lines, phrase }: { expressionId: number; lines: KoreanLine[]; phrase: string }) {
  const [english, setEnglish] = useSharedView<boolean>(`dialogue:${expressionId}`, false)
  return (
    <button type="button" className="korean-example-card korean-dialogue-card" aria-pressed={english} onClick={() => setEnglish(!english)}>
      {lines.map((line, i) => (
        <span key={i} className="korean-dialogue-line">
          <span className="korean-dialogue-speaker">{i === 0 ? 'A' : 'B'}</span>
          {english ? (
            <span className="korean-example-english">
              <Marked text={line.english} word={phrase} />
            </span>
          ) : (
            <span className="korean-example-korean" lang="ko">
              {line.korean}
            </span>
          )}
        </span>
      ))}
      <span className="korean-example-hint">{english ? ENGLISH_HINT : KOREAN_HINT}</span>
    </button>
  )
}
