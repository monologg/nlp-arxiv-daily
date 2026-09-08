import type { ParsedPaper } from "./paperRow.ts";

/**
 * COinS (ContextObjects in Spans) descriptor for one paper.
 *
 * Zotero's connector scans a page for `<span class="Z3988" title="...">`
 * and offers every match in its multi-select save dialog — the only way
 * to make a *list* page importable, since Highwire `citation_*` meta
 * tags describe a single item per page.
 *
 * Field choices follow zotero/utilities openurl.js `parseContextObject`:
 *  - `mtx:dc` + `rft.type=preprint` → Zotero "Preprint" item
 *  - `rft.creator` → author, `rft.date` → date, `rft.source` → repository
 *  - `rft_id=info:doi/…` → DOI (every arXiv paper has a DataCite DOI)
 *  - `rft_id=https://…` → URL, `rft.subject` → tag
 */
export function coinsTitle(paperId: string, paper: ParsedPaper, keyword?: string): string {
  const parts: Array<[string, string]> = [
    ["ctx_ver", "Z39.88-2004"],
    ["rft_val_fmt", "info:ofi/fmt:kev:mtx:dc"],
    ["rft.type", "preprint"],
    ["rft.title", paper.title],
    ["rft.creator", paper.firstAuthor],
    ["rft.date", paper.date],
    ["rft.source", "arXiv"],
    ["rft_id", `info:doi/10.48550/arXiv.${paperId}`],
    ["rft_id", paper.paperUrl],
  ];
  if (keyword) parts.push(["rft.subject", keyword]);
  return parts.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
}
