import type { Article } from '../types'

export function ArticleTab({ article }: { article: Article }) {
  const paragraphs = article.body.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read silently for three minutes. Then each of you summarizes the article in your own words before opening the
        questions.
      </p>
      <article className="article">
        <h2 className="article-title">{article.title}</h2>
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </article>
      <details className="questions">
        <summary>Discussion questions</summary>
        <ol>
          {article.questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ol>
      </details>
    </section>
  )
}
