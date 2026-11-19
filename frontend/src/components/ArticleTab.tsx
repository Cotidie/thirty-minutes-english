import { Fragment, useState } from "react";
import { pairSentences } from "../lib/sentences";
import { useReadingMarks } from "../lib/useReadingMarks";
import { useSummaries } from "../lib/useSummaries";
import type { Article, Figure } from "../types";
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
  /** The paragraph holding the microphone. */
  const [reading, setReading] = useState<number | null>(null);
  const { summaries, add: addSummary } = useSummaries(sessionId);
  const { marks, add: addReading } = useReadingMarks(sessionId);
  const paragraphs = article.paragraphs;
  const cover = (article.figures ?? []).find((f) => f.paragraph_id === null);
  const sentences = pairSentences(
    paragraphs.map((p) => p.text),
    article.translation ?? [],
  );

  return (
    <section className="tab-panel">
      <p className="tab-brief" data-presence-anchor="brief">
        Read it, then each of you sums it up in your own words before the
        question. Click a sentence for the Korean.
      </p>
      <article className="article">
        <h2 className="article-title" data-presence-anchor="title">{article.title}</h2>
        {cover && <ArticleFigure figure={cover} />}
        {paragraphs.map((p, i) => (
          <Fragment key={p.id}>
            <Paragraph
              paragraph={p}
              pieces={sentences[i]}
              summaries={summaries.filter((s) => s.paragraph_id === p.id)}
              saved={marks.get(p.id) ?? NO_MARKS}
              onSummary={addSummary}
              onReading={addReading}
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
      {article.question && (
        <section className="discussion">
          <h3>Discussion question</h3>
          <p data-presence-anchor="question">{article.question}</p>
        </section>
      )}
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

/** An image under its paragraph or the title, with where it came from: the page and who it credits, or that it was drawn for the article. */
function ArticleFigure({ figure }: { figure: Figure }) {
  const from = figure.source_url
    ? [figure.credit, hostOf(figure.source_url)].filter(Boolean).join(" · ")
    : null;
  return (
    <figure className="article-figure" data-presence-anchor={`figure:${figure.id}`}>
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
