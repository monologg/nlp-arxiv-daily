/**
 * Keyword → URL/anchor slug. Single source of truth so section anchors,
 * the filter pills, and the `.bib` download routes always agree.
 */
export function keywordSlug(keyword: string): string {
  return keyword.toLowerCase().replace(/\s+/g, "-");
}
