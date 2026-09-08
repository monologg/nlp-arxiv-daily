import { parsePaper, type ParsedPaper, type PaperValue } from "./paperRow.ts";

/**
 * BibTeX export.
 *
 * Dict records carry the full author list, abstract and arxiv categories,
 * so those entries are complete. Legacy string rows only know the first
 * author and become `author = {First Author and others}` — BibTeX renders
 * "and others" as "et al.", which is the honest representation of what we
 * have; arXiv's own export (https://arxiv.org/bibtex/<id>) has the rest.
 */

export interface BibEntry {
  paperId: string;
  paper: ParsedPaper;
  /** Every keyword section this paper appeared under. */
  keywords: string[];
}

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

// Words that make for a useless cite key ("the2026paper").
const KEY_STOPWORDS = new Set(["a", "an", "the", "on", "of", "in", "to", "for", "and", "towards", "toward", "from", "with"]);

function asciiToken(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

/** Google-Scholar-style key: `<lastname><year><firstTitleWord>`. */
export function citeKey(paperId: string, paper: ParsedPaper): string {
  const authorTokens = paper.firstAuthor.trim().split(/\s+/);
  const last = asciiToken(authorTokens[authorTokens.length - 1] ?? "");
  const year = paper.date.slice(0, 4);
  const titleWord =
    paper.title
      .split(/\s+/)
      .map(asciiToken)
      .find((w) => w.length > 0 && !KEY_STOPWORDS.has(w)) ?? "";
  const key = `${last}${year}${titleWord}`;
  return key.length > 4 ? key : `arxiv${paperId.replace(/[^0-9a-z]/gi, "")}`;
}

/**
 * Escape LaTeX-special characters in a title. Titles that already contain
 * `$` are assumed to carry inline math and are passed through untouched —
 * escaping `_`/`^` inside math would break it, and arXiv titles are LaTeX
 * to begin with.
 */
export function escapeTitle(title: string): string {
  if (title.includes("$")) return title;
  return title.replace(/(?<!\\)([&%#_^])/g, "\\$1");
}

/** Abstracts are prose, not LaTeX: escape braces and the usual specials. */
export function escapeAbstract(text: string): string {
  return text.replace(/[\\{}]/g, "\\$&").replace(/([&%#_])/g, "\\$1");
}

export function formatEntry(entry: BibEntry, key: string): string {
  const { paperId, paper, keywords } = entry;
  const year = paper.date.slice(0, 4);
  const month = MONTHS[Number(paper.date.slice(5, 7)) - 1];
  const author =
    paper.authors.length > 0 ? paper.authors.join(" and ") : `${paper.firstAuthor} and others`;
  const fields: Array<[string, string]> = [
    ["title", `{${escapeTitle(paper.title)}}`],
    ["author", `{${author}}`],
    ["year", `{${year}}`],
    ["month", month ?? ""],
    ["eprint", `{${paperId}}`],
    ["archivePrefix", "{arXiv}"],
    ["primaryClass", paper.categories[0] ? `{${paper.categories[0]}}` : ""],
    ["url", `{${paper.paperUrl}}`],
  ];
  if (paper.codeLink) fields.push(["note", `{Code: \\url{${paper.codeLink}}}`]);
  if (keywords.length > 0) fields.push(["keywords", `{${keywords.join(", ")}}`]);
  if (paper.abstract) fields.push(["abstract", `{${escapeAbstract(paper.abstract)}}`]);

  const width = Math.max(...fields.map(([k]) => k.length));
  const body = fields
    .filter(([, v]) => v.length > 0)
    .map(([k, v]) => `  ${k.padEnd(width)} = ${v},`)
    .join("\n");
  return `@misc{${key},\n${body}\n}`;
}

/**
 * Build a `.bib` document from keyword buckets. A paper matched by several
 * keywords is emitted once, with all of them in its `keywords` field. Cite
 * keys are de-duplicated with a/b/c suffixes.
 */
export function buildBib(buckets: Array<[string, Record<string, PaperValue>]>, header?: string): string {
  const byId = new Map<string, BibEntry>();
  for (const [keyword, papers] of buckets) {
    for (const [paperId, row] of Object.entries(papers)) {
      const existing = byId.get(paperId);
      if (existing) {
        existing.keywords.push(keyword);
        continue;
      }
      const paper = parsePaper(row);
      if (!paper) continue;
      byId.set(paperId, { paperId, paper, keywords: [keyword] });
    }
  }

  const entries = Array.from(byId.values()).sort((a, b) =>
    a.paperId < b.paperId ? 1 : a.paperId > b.paperId ? -1 : 0,
  );

  const seen = new Map<string, number>();
  const blocks = entries.map((entry) => {
    const base = citeKey(entry.paperId, entry.paper);
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    const key = n === 0 ? base : `${base}${String.fromCharCode(96 + n)}`;
    return formatEntry(entry, key);
  });

  const preamble = header ? `% ${header}\n% ${entries.length} entries\n\n` : "";
  return preamble + blocks.join("\n\n") + "\n";
}

/** Single-paper BibTeX for the per-card copy button. */
export function paperBibtex(paperId: string, paper: ParsedPaper): string {
  return formatEntry({ paperId, paper, keywords: [] }, citeKey(paperId, paper));
}
