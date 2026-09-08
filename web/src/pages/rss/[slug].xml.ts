import type { APIContext } from "astro";
import { KEYWORD_FEED_LIMIT, buildFeedItems, feedResponse } from "../../utils/feed.ts";
import { keywordSlug } from "../../utils/keyword.ts";
import { resolveLatest, type KeywordEntries } from "../../utils/papers.ts";

/** /rss/<keyword-slug>.xml — one keyword section of the Latest page. */
export async function getStaticPaths() {
  const { keywords } = resolveLatest();
  return keywords.map(([keyword, papers]) => ({
    params: { slug: keywordSlug(keyword) },
    props: { keyword, buckets: [[keyword, papers]] as KeywordEntries },
  }));
}

export async function GET(context: APIContext) {
  const { keyword, buckets } = context.props as { keyword: string; buckets: KeywordEntries };
  return feedResponse(context, {
    title: `NLP Arxiv Daily — ${keyword}`,
    description: `Daily-refreshed arxiv papers matching "${keyword}"`,
    items: buildFeedItems(buckets, KEYWORD_FEED_LIMIT),
  });
}
