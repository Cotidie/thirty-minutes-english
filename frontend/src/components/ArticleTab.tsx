import { Fragment, useEffect, useRef, useState } from "react";
import { markedSpans } from "../lib/highlight";
import { pairSentences } from "../lib/sentences";
import { useReadingMarks } from "../lib/useReadingMarks";
import { useSummaries } from "../lib/useSummaries";
import type { Article, Figure, Question } from "../types";
import { Paragraph } from "./Paragraph";
import "./ArticleTab.css";

const NO_MARKS: never[] = [];

export function ArticleTab({
  article,
  sessionId,
}: {
  article: Article;
  sessionId: number;
}) {
  const [active, setActive] = useState<number | null>(null);
  /** The paragraph holding the microphone. */
  const [reading, setReading] = useState<number | null>(null);
  const bodyRef = useRef<HTMLElement>(null);
  const { summaries, add: addSummary } = useSummaries(sessionId);
  const marks = useReadingMarks(sessionId);
  const paragraphs = article.paragraphs;
  const cover = (article.figures ?? []).find((f) => f.paragraph_id === null);
  const sentences = pairSentences(
    paragraphs.map((p) => p.text),
    article.translation ?? [],
  );
  const evidence = active === null ? [] : article.questions[active].evidence;

  useEffect(() => {
    bodyRef.current
      ?.querySelector("mark")
      ?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [active]);

  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read it, then each of you sums it up in your own words before the
        questions. Click a sentence for the Korean, a question for its passage.
      </p>
      <article className="article" ref={bodyRef}>
        <h2 className="article-title">{article.title}</h2>
        {cover && <ArticleFigure figure={cover} />}
        {paragraphs.map((p, i) => (
          <Fragment key={p.id}>
            <Paragraph
              paragraph={p}
              pieces={sentences[i]}
              spans={markedSpans(p.text, evidence)}
              summaries={summaries.filter((s) => s.paragraph_id === p.id)}
              saved={marks.get(p.id) ?? NO_MARKS}
              onSummary={addSummary}
              active={reading !== null && reading !== i}
              onStart={() => setReading(i)}
              onEnd={() => setReading(null)}
            />
            {(article.figures ?? [])
              .filter((f) => f.paragraph_id === p.id)
              .map((f) => (
                <ArticleFigure key={f.id} figure={f} />
              ))}
          </Fragment>
        ))}
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

/** An image under its paragraph or the title, with where it came from: the page and who it credits, or that it was drawn for the article. */
function ArticleFigure({ figure }: { figure: Figure }) {
  const from = figure.source_url
    ? [figure.credit, hostOf(figure.source_url)].filter(Boolean).join(" · ")
    : null;
  return (
    <figure className="article-figure">
      <img
        src={`/api/images/${figure.image}`}
        alt={figure.caption}
        loading="lazy"
      />
      <figcaption>
        {figure.caption}{" "}
        {figure.source_url ? (
          <a
            className="figure-source"
            href={figure.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {from}
          </a>
        ) : (
          <span className="figure-source">Drawn for this article</span>
        )}
      </figcaption>
    </figure>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
