/**
 * Parse a legacy markdown paper row into structured fields.
 *
 * The Python pipeline (PRSL-66 renderer + cli) emits rows shaped like:
 *
 *   "- 2026-04-22, **Title**, Author et.al., Paper: [url](url)\n"
 *
 * or with a code link appended:
 *
 *   "- 2026-04-22, **Title**, Author et.al., Paper: [url](url), Code: **[ghurl](ghurl)**\n"
 *
 * This parser is the read-side counterpart to `core.papers_to_legacy_rows`
 * on the Python side. The legacy markdown format is the JSON contract for
 * now; later tickets may flip to structured Paper JSON, at which point this
 * util goes away.
 */
export interface ParsedPaper {
  date: string; // ISO YYYY-MM-DD
  title: string;
  firstAuthor: string;
  paperUrl: string;
  codeLink: string | null;
}

const ROW_RE =
  // Anchor on the leading "- ", capture date, title, author, paper url, and optional code link.
  /^-\s+(\d{4}-\d{2}-\d{2}),\s+\*\*(.+?)\*\*,\s+(.+?)\s+et\.al\.,\s+Paper:\s+\[(.+?)\]\(.+?\)(?:,\s+Code:\s+\*\*\[(.+?)\]\(.+?\)\*\*)?\s*$/;

export function parsePaperRow(row: string): ParsedPaper | null {
  const match = row.trim().match(ROW_RE);
  if (!match) return null;
  const [, date, title, firstAuthor, paperUrl, codeLink] = match;
  return {
    date,
    title,
    firstAuthor,
    paperUrl,
    codeLink: codeLink ?? null,
  };
}

/**
 * Sort papers within a keyword section: newest paper id first (which mirrors
 * what the Python renderer does, since arxiv ids are monotonic by submission).
 */
export function sortPapersDesc(papers: Record<string, string>): Array<[string, string]> {
  return Object.entries(papers).sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0));
}
