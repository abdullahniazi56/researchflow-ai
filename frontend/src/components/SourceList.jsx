function normalize(item, index) {
  const url = item.url || item.source_url || null;
  const name =
    item.source ||
    item.source_name ||
    item.name ||
    item.title ||
    `Source ${index + 1}`;
  const page = item.page ?? item.page_number ?? null;
  const type =
    item.type || item.source_type || (url ? "web" : "document");
  const excerpt = (item.snippet || item.content || "").trim();

  return { url, name, page, type, excerpt, cited: item.cited };
}

function domainOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function SourceRows({ sources, start = 0 }) {
  return sources.map((source, index) => {
    const isWeb = source.type === "web";
    const meta = isWeb
      ? domainOf(source.url)
      : source.page != null
        ? `Page ${source.page}`
        : "Document";

    return (
      <li key={`${source.name}-${source.page}-${index}`}>
        <details>
          <summary>
            <span className="source-index">{start + index + 1}</span>
            <span className={`source-kind ${isWeb ? "kind-web" : "kind-doc"}`}>
              {isWeb ? "Web" : "PDF"}
            </span>
            <span className="source-title">{source.name}</span>
            <span className="source-where">{meta}</span>
          </summary>

          <div className="source-detail">
            {source.excerpt && <p className="source-excerpt">{source.excerpt}</p>}
            {source.url && (
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                Open {domainOf(source.url)}
              </a>
            )}
          </div>
        </details>
      </li>
    );
  });
}

export default function SourceList({ items }) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }

  // one row per source, not per chunk
  const seen = new Set();
  const sources = [];

  items.forEach((item, index) => {
    const source = normalize(item, index);
    const key = `${source.name}|${source.url}|${source.page}`;
    if (!seen.has(key)) {
      seen.add(key);
      sources.push(source);
    }
  });

  // cited sources first, the rest folded away
  const hasCitedFlag = sources.some((s) => s.cited !== undefined);
  const cited = hasCitedFlag ? sources.filter((s) => s.cited) : sources;
  const others = hasCitedFlag ? sources.filter((s) => !s.cited) : [];
  const shown = cited.length ? cited : others;
  const folded = cited.length ? others : [];

  return (
    <section className="source-list" aria-label="Sources">
      <h3>
        Sources <span>{shown.length}</span>
      </h3>

      <ol>
        <SourceRows sources={shown} />
      </ol>

      {folded.length > 0 && (
        <details className="other-sources">
          <summary>
            {folded.length} more searched but not cited
          </summary>
          <ol>
            <SourceRows sources={folded} start={shown.length} />
          </ol>
        </details>
      )}
    </section>
  );
}
