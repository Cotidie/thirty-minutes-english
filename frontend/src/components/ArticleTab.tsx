import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { markedSpans, segmentsIn } from "../lib/highlight";
import { pairSentences } from "../lib/sentences";
import type { Article, Question } from "../types";
import { ReadAloud } from "./ReadAloud";
import { ReadingText } from "./ReadingText";
import { Run, Sentence } from "./Sentence";

/** One paragraph's slashes: asked for, shown or hidden. */
interface Phrasing {
  on: boolean;
  breaks?: number[];
  loading?: boolean;
  error?: string;
}

export function ArticleTab({
  article,
  sessionId,
}: {
  article: Article;
  sessionId: number | null;
}) {
  const [active, setActive] = useState<number | null>(null);
  const [reading, setReading] = useState<number | null>(null);
  /** Paragraphs still showing their read-aloud marks after the round. */
  const [marked, setMarked] = useState<Set<number>>(new Set());
  const [phrasing, setPhrasing] = useState<Record<number, Phrasing>>({});
  const bodyRef = useRef<HTMLElement>(null);
  const paragraphs = article.body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  const sentences = pairSentences(paragraphs, article.translation ?? []);
  const evidence = active === null ? [] : article.questions[active].evidence;

  useEffect(() => {
    bodyRef.current
      ?.querySelector("mark")
      ?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [active]);

  /** Slashes on or off for one paragraph; the first time asks the backend where they go. */
  const togglePhrasing = async (i: number) => {
    const current = phrasing[i];
    if (current?.breaks)
      return setPhrasing((s) => ({
        ...s,
        [i]: { ...current, on: !current.on },
      }));
    setPhrasing((s) => ({ ...s, [i]: { on: true, loading: true } }));
    try {
      const { breaks } = await api.phrasing(paragraphs[i]);
      setPhrasing((s) => ({ ...s, [i]: { on: true, breaks } }));
    } catch (e) {
      setPhrasing((s) => ({
        ...s,
        [i]: { on: false, error: e instanceof Error ? e.message : String(e) },
      }));
    }
  };

  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read it, then each of you sums it up in your own words before the
        questions. Click a sentence for the Korean, a question for its passage.
      </p>
      <article className="article" ref={bodyRef}>
        <h2 className="article-title">{article.title}</h2>
        {paragraphs.map((p, i) => {
          const spans = markedSpans(p, evidence);
          const phrased = phrasing[i];
          const breaks = phrased?.on ? phrased.breaks : undefined;
          const readAloudShows = reading === i || marked.has(i);
          return (
            <div key={i} className="paragraph">
              {breaks && !readAloudShows && (
                <ReadingText
                  paragraph={p}
                  findings={[]}
                  breaks={breaks}
                  open={null}
                  onOpen={() => undefined}
                />
              )}
              <p hidden={readAloudShows || breaks !== undefined}>
                {sentences[i].map((piece, j) => {
                  const segments = segmentsIn(piece.text, spans, piece.start);
                  return piece.ko === null ? (
                    <Run key={j} segments={segments} />
                  ) : (
                    <Sentence key={j} segments={segments} ko={piece.ko} />
                  );
                })}
              </p>
              <div className="paragraph-tools">
                <button
                  type="button"
                  className={`phrasing-toggle${phrased?.on ? " is-on" : ""}`}
                  aria-pressed={phrased?.on ?? false}
                  disabled={phrased?.loading}
                  onClick={() => void togglePhrasing(i)}
                >
                  {phrased?.loading ? "Marking…" : "Phrasing"}
                </button>
                {phrased?.error && (
                  <span className="phrasing-error">{phrased.error}</span>
                )}
                <ReadAloud
                  paragraph={p}
                  breaks={phrased?.breaks}
                  sessionId={sessionId}
                  active={reading !== null && reading !== i}
                  onStart={() => setReading(i)}
                  onEnd={(kept) => {
                    setReading(null);
                    setMarked((m) => {
                      const next = new Set(m);
                      if (kept) next.add(i);
                      else next.delete(i);
                      return next;
                    });
                  }}
                />
              </div>
            </div>
          );
        })}
      </article>
      <section className="questions">
        <h3>Discussion questions</h3>
        <ol>
          {article.questions.map((q, i) => (
            <li key={q.text}>
              <QuestionItem
                question={q}
                active={active === i}
                onToggle={() => setActive(active === i ? null : i)}
              />
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
  );
}

function QuestionItem({
  question,
  active,
  onToggle,
}: {
  question: Question;
  active: boolean;
  onToggle: () => void;
}) {
  // Nothing in the article answers it, so there is no passage to point at.
  if (question.evidence.length === 0) {
    return (
      <span className="question is-open">
        {question.text}
        <span className="question-tag">your take</span>
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`question${active ? " is-active" : ""}`}
      aria-pressed={active}
      onClick={onToggle}
    >
      {question.text}
    </button>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
