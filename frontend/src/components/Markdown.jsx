// Small markdown renderer. Builds React elements (no innerHTML), so model
// output can't inject HTML. Also turns [Source: file, Page: n] into chips.

const OPEN = "⟦"; // placeholders for escaped \[ and \]
const CLOSE = "⟧";

const INLINE =
  /(\[Source:[^\]]+\]|\[[^\]]+\]\((https?:\/\/[^\s)]+)\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;

function restore(text) {
  return text.replaceAll(OPEN, "[").replaceAll(CLOSE, "]");
}

function renderInline(text, keyPrefix) {
  const parts = [];
  let last = 0;
  let match;
  let i = 0;

  INLINE.lastIndex = 0;

  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(restore(text.slice(last, match.index)));
    }

    const token = match[0];
    const key = `${keyPrefix}-${i++}`;

    if (token.startsWith("[Source:")) {
      const inner = token.slice(8, -1).trim();
      const [file, page] = inner.split(/,\s*Page:\s*/);
      parts.push(
        <span className="cite cite-doc" key={key} title={restore(inner)}>
          {restore(file)}
          {page ? `, p. ${page}` : ""}
        </span>
      );
    } else if (token.startsWith("[")) {
      const label = token.slice(1, token.indexOf("]("));
      const url = match[2];
      parts.push(
        <a
          className="cite cite-web"
          href={url}
          key={key}
          target="_blank"
          rel="noopener noreferrer"
          title={url}
        >
          {restore(label)}
        </a>
      );
    } else if (token.startsWith("**")) {
      parts.push(<strong key={key}>{restore(token.slice(2, -2))}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(<code key={key}>{restore(token.slice(1, -1))}</code>);
    } else {
      parts.push(<em key={key}>{restore(token.slice(1, -1))}</em>);
    }

    last = match.index + token.length;
  }

  if (last < text.length) {
    parts.push(restore(text.slice(last)));
  }

  return parts;
}

export default function Markdown({ text }) {
  if (!text) return null;

  const lines = text
    .replaceAll("\\[", OPEN)
    .replaceAll("\\]", CLOSE)
    .split(/\r?\n/);

  const blocks = [];
  let paragraph = [];
  let list = null; // { type: "ul" | "ol", items: [] }

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: "p", text: paragraph.join(" ") });
      paragraph = [];
    }
  };

  const flushList = () => {
    if (list) {
      blocks.push(list);
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trim();

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = line.match(/^#{1,6}\s+(.*)$/);
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);

    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h", text: heading[1] });
    } else if (bullet || numbered) {
      flushParagraph();
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        flushList();
        list = { type, items: [] };
      }
      list.items.push((bullet || numbered)[1]);
    } else {
      flushList();
      paragraph.push(line);
    }
  }

  flushParagraph();
  flushList();

  return (
    <div className="markdown">
      {blocks.map((block, index) => {
        const key = `b${index}`;

        if (block.type === "h") {
          return <h4 key={key}>{renderInline(block.text, key)}</h4>;
        }

        if (block.type === "ul" || block.type === "ol") {
          const List = block.type;
          return (
            <List key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {renderInline(item, `${key}-${itemIndex}`)}
                </li>
              ))}
            </List>
          );
        }

        return <p key={key}>{renderInline(block.text, key)}</p>;
      })}
    </div>
  );
}
