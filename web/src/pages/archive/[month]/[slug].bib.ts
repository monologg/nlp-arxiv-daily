import type { APIRoute } from "astro";
import { buildBib } from "../../../utils/bibtex.ts";
import { keywordSlug } from "../../../utils/keyword.ts";
import { keywordStats, listMonths, loadMonth, nonEmptyKeywords } from "../../../utils/papers.ts";

/**
 * /archive/<YYYY-MM>/<keyword-slug>.bib — one keyword section of a month.
 * /archive/<YYYY-MM>/all.bib          — the whole month, de-duplicated.
 * Paths carry ids only; the month is loaded at render time.
 */
export async function getStaticPaths() {
  return listMonths().flatMap((month) => {
    const paths = keywordStats(month).map(({ keyword }) => ({
      params: { month, slug: keywordSlug(keyword) },
      props: { month, keyword },
    }));
    paths.push({ params: { month, slug: "all" }, props: { month, keyword: null } });
    return paths;
  });
}

export const GET: APIRoute = ({ props }) => {
  const { month, keyword } = props as { month: string; keyword: string | null };
  const data = loadMonth(month);
  const buckets = keyword ? nonEmptyKeywords(data).filter(([k]) => k === keyword) : nonEmptyKeywords(data);
  const header = `NLP Arxiv Daily — ${keyword ?? "all keywords"} (${month})`;
  return new Response(buildBib(buckets, header), {
    headers: { "Content-Type": "application/x-bibtex; charset=utf-8" },
  });
};
