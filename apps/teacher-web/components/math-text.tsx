import katex from "katex";

export type MathTextPart = {
  kind: "text" | "inline-math" | "display-math";
  value: string;
};

const EXPLICIT_MATH = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$)/g;
const LEGACY_MATH_RUN = /[A-Za-z0-9\\π∞Σ∑∫√±≤≥≠≈→←↔∈∉⊂⊆∪∩∏][A-Za-z0-9\\π∞Σ∑∫√±≤≥≠≈→←↔∈∉⊂⊆∪∩∏+\-*/=<>^_()[\]{}|.,:;\s]*/gu;
const STRONG_MATH_SIGNAL = /\\[A-Za-z]+|[=+\-*/^_<>≤≥≠≈∑Σ∫√±]|\d\s*\/\s*\w|[A-Za-z]\w*\s*\(/u;

function appendText(parts: MathTextPart[], value: string) {
  if (!value) return;
  const previous = parts.at(-1);
  if (previous?.kind === "text") {
    previous.value += value;
    return;
  }
  parts.push({ kind: "text", value });
}

function legacyParts(text: string): MathTextPart[] {
  const parts: MathTextPart[] = [];
  let cursor = 0;

  for (const match of text.matchAll(LEGACY_MATH_RUN)) {
    const raw = match[0];
    const start = match.index;
    const value = raw.trimEnd();
    if (!value || !STRONG_MATH_SIGNAL.test(value)) continue;

    appendText(parts, text.slice(cursor, start));
    parts.push({ kind: "inline-math", value });
    appendText(parts, raw.slice(value.length));
    cursor = start + raw.length;
  }

  appendText(parts, text.slice(cursor));
  return parts;
}

function explicitPart(token: string): MathTextPart {
  if (token.startsWith("$$")) {
    return { kind: "display-math", value: token.slice(2, -2).trim() };
  }
  if (token.startsWith(String.raw`\[`)) {
    return { kind: "display-math", value: token.slice(2, -2).trim() };
  }
  if (token.startsWith(String.raw`\(`)) {
    return { kind: "inline-math", value: token.slice(2, -2).trim() };
  }
  return { kind: "inline-math", value: token.slice(1, -1).trim() };
}

export function parseMathText(text: string): MathTextPart[] {
  const parts: MathTextPart[] = [];
  let cursor = 0;

  for (const match of text.matchAll(EXPLICIT_MATH)) {
    const start = match.index;
    parts.push(...legacyParts(text.slice(cursor, start)));
    parts.push(explicitPart(match[0]));
    cursor = start + match[0].length;
  }

  parts.push(...legacyParts(text.slice(cursor)));
  return parts.filter((part) => part.value.length > 0);
}

function RenderedMath({ part }: { part: MathTextPart }) {
  const displayMode = part.kind === "display-math";
  try {
    const html = katex.renderToString(part.value, {
      displayMode,
      throwOnError: true,
      strict: "ignore",
      trust: false,
      output: "htmlAndMathml",
    });
    return (
      <span
        className={displayMode ? "math-display" : "inline-math"}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return (
      <span className={displayMode ? "math-fallback math-fallback--display" : "math-fallback"}>
        {part.value}
      </span>
    );
  }
}

export function MathText({ text }: { text: string }) {
  return (
    <span className="math-text">
      {parseMathText(text).map((part, index) => (
        part.kind === "text"
          ? <span key={index}>{part.value}</span>
          : <RenderedMath key={index} part={part} />
      ))}
    </span>
  );
}
