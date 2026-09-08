import type { APIContext } from "astro";
import { buildFeedItems, feedResponse } from "../utils/feed.ts";
import { resolveLatest } from "../utils/papers.ts";

/** /rss.xml — every keyword. Per-keyword feeds live at /rss/<slug>.xml. */
export async function GET(context: APIContext) {
  const { keywords } = await resolveLatest();
  return feedResponse(context, {
    title: "NLP Arxiv Daily",
    description: "Daily-refreshed NLP arxiv paper digest",
    items: buildFeedItems(keywords),
  });
}
