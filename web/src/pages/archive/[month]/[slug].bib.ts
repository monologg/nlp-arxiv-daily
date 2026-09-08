import type { APIRoute } from "astro";
import { buildBib } from "../../../utils/bibtex.ts";
import { keywordSlug } from "../../../utils/keyword.ts";
import { allMonths, nonEmptyKeywords, type KeywordEntries } from "../../../utils/papers.ts";

/**
 * /archive/<YYYY-MM>/<keyword-slug>.bib — one keyword section of a month.
 * /archive/<YYYY-MM>/all.bib          — the whole month, de-duplicated.
 */
export async function getStaticPaths() {
  const entries = await allMonths();
  return entries.flatMap((entry) => {
    const keywords = nonEmptyKeywords(entry.data);
    const paths = keywords.map(([keyword, papers]) => ({
      params: { month: entry.id, slug: keywordSlug(keyword) },
      props: { buckets: [[keyword, papers]] as KeywordEntries, header: `NLP Arxiv Daily — ${keyword} (${entry.id})` },
    }));
    paths.push({
      params: { month: entry.id, slug: "all" },
      props: { buckets: keywords, header: `NLP Arxiv Daily — all keywords (${entry.id})` },
    });
    return paths;
  });
}

export const GET: APIRoute = ({ props }) => {
  const { buckets, header } = props as { buckets: KeywordEntries; header: string };
  return new Response(buildBib(buckets, header), {
    headers: { "Content-Type": "application/x-bibtex; charset=utf-8" },
  });
};
