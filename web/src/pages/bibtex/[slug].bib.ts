import type { APIRoute } from "astro";
import { buildBib } from "../../utils/bibtex.ts";
import { keywordSlug } from "../../utils/keyword.ts";
import { resolveLatest, type KeywordEntries } from "../../utils/papers.ts";

/**
 * /bibtex/<keyword-slug>.bib — every paper in one "Latest" keyword section
 *                              (the whole month, not just the cards shown).
 * /bibtex/all.bib          — the whole Latest month, de-duplicated.
 */
export async function getStaticPaths() {
  const { keywords, monthId } = resolveLatest();
  const label = monthId ?? "latest";
  const paths = keywords.map(([keyword, papers]) => ({
    params: { slug: keywordSlug(keyword) },
    props: { buckets: [[keyword, papers]] as KeywordEntries, header: `NLP Arxiv Daily — ${keyword} (${label})` },
  }));
  paths.push({
    params: { slug: "all" },
    props: { buckets: keywords, header: `NLP Arxiv Daily — all keywords (${label})` },
  });
  return paths;
}

export const GET: APIRoute = ({ props }) => {
  const { buckets, header } = props as { buckets: KeywordEntries; header: string };
  return new Response(buildBib(buckets, header), {
    headers: { "Content-Type": "application/x-bibtex; charset=utf-8" },
  });
};
