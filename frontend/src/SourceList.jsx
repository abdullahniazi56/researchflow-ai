/*
  Compact list of the sources behind an answer.
  Works for both live research evidence and saved sources from the DB.
  Each row shows: number, PDF/Web badge, title, page or domain.
  The excerpt opens on click (native <details>, keyboard accessible).
*/

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

  return { url, name, page, type, excerpt };
}

function domainOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function SourceList({ items }) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }

  // The same document page can appear several times (one per chunk).
  // Show each source once.
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

  return (
    <section className="source-list" aria-label="Sources">
      <h3>
        Sources <span>{sources.length}</span>
      </h3>

      <ol>
        {sources.map((source, index) => {
          const isWeb = source.type === "web";
          const meta = isWeb
            ? domainOf(source.url)
            : source.page != null
              ? `Page ${source.page}`
              : "Document";

          return (
            <li key={`${source.name}-${index}`}>
              <details>
                <summary>
                  <span className="source-index">{index + 1}</span>

                  <span
                    className={`source-kind ${
                      isWeb ? "kind-web" : "kind-doc"
                    }`}
                  >
                    {isWeb ? "Web" : "PDF"}
                  </span>

                  <span className="source-title">{source.name}</span>

                  <span className="source-where">{meta}</span>
                </summary>

                <div className="source-detail">
                  {source.excerpt && (
                    <p className="source-excerpt">{source.excerpt}</p>
                  )}

                  {source.url && (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open {domainOf(source.url)}
                    </a>
                  )}
                </div>
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
