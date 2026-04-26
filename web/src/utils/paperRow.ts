/**
 * Parse a legacy markdown paper row into structured fields.
 *
 * The Python pipeline historically emitted TWO row formats and the
 * gitpage-flavor archive JSONs ended up with both mixed in: bullet rows
 * for recent backfilled months, pipe-table rows for everything older.
 *
 * Bullet (gitpage):
 *   "- 2026-04-22, **Title**, Author et.al., Paper: [url](url)"
 *   "- 2026-04-22, **Title**, Author et.al., Paper: [url](url), Code: **[ghurl](ghurl)**"
 *
 * Pipe (README, leaked into pre-2025-08 archive-web JSONs during the
 * original backfill migration):
 *   "|**2025-06-03**|**Title**|Author et.al.|[2506.02818v1](url)|null|"
 *   "|**2025-06-03**|**Title**|Author et.al.|[id](url)|**[link](ghurl)**|"
 *
 * We try the bullet regex first (preferred shape) and fall back to pipe.
 * Either way the parser is the read-side counterpart to
 * `core.papers_to_legacy_rows`.
 */
export interface ParsedPaper {
  date: string; // ISO YYYY-MM-DD
  title: string;
  firstAuthor: string;
  paperUrl: string;
  codeLink: string | null;
}

const BULLET_RE =
  /^-\s+(\d{4}-\d{2}-\d{2}),\s+\*\*(.+?)\*\*,\s+(.+?)\s+et\.al\.,\s+Paper:\s+\[(.+?)\]\(.+?\)(?:,\s+Code:\s+\*\*\[(.+?)\]\(.+?\)\*\*)?\s*$/;

const PIPE_RE =
  /^\|\*\*(\d{4}-\d{2}-\d{2})\*\*\|\*\*(.+?)\*\*\|(.+?)\s+et\.al\.\|\[.+?\]\((.+?)\)\|(.+?)\|\s*$/;

export function parsePaperRow(row: string): ParsedPaper | null {
  const trimmed = row.trim();

  const bullet = trimmed.match(BULLET_RE);
  if (bullet) {
    const [, date, title, firstAuthor, paperUrl, codeLink] = bullet;
    return { date, title, firstAuthor, paperUrl, codeLink: codeLink ?? null };
  }

  const pipe = trimmed.match(PIPE_RE);
  if (pipe) {
    const [, date, title, firstAuthor, paperUrl, codeCell] = pipe;
    // Pipe code cell is either "null" or "**[link](codeUrl)**".
    const codeMatch = codeCell.match(/\*\*\[.+?\]\((.+?)\)\*\*/);
    return {
      date,
      title,
      firstAuthor,
      paperUrl,
      codeLink: codeMatch ? codeMatch[1] : null,
    };
  }

  return null;
}

/**
 * Sort papers within a keyword section: newest paper id first (which mirrors
 * what the Python renderer does, since arxiv ids are monotonic by submission).
 */
export function sortPapersDesc(papers: Record<string, string>): Array<[string, string]> {
  return Object.entries(papers).sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0));
}
