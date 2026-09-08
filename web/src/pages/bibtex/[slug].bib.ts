import type { APIRoute } from "astro";
import { buildBib } from "../../utils/bibtex.ts";
import { keywordSlug } from "../../utils/keyword.ts";
import { resolveRecent, type KeywordEntries } from "../../utils/papers.ts";

/**
 * /bibtex/<keyword-slug>.bib — one keyword section of the Latest page.
 * /bibtex/all.bib          — the whole Latest page, de-duplicated.
 * Both cover the same day window the page shows; whole months live at
 * /archive/<YYYY-MM>/<slug>.bib.
 */
export async function getStaticPaths() {
  const { keywords, windowDays, since, monthId, widened } = await resolveRecent();
  const label = widened ? `all of ${monthId}` : `last ${windowDays} days, since ${since}`;
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
