import { SITE_NAME } from "../config.ts";
import type { APIContext } from "astro";
import { MAIN_FEED_LIMIT, buildFeedItems, feedResponse } from "../utils/feed.ts";
import { resolveLatest } from "../utils/papers.ts";

/** /rss.xml — every keyword. Per-keyword feeds live at /rss/<slug>.xml. */
export async function GET(context: APIContext) {
  const { keywords } = resolveLatest();
  return feedResponse(context, {
    title: SITE_NAME,
    description: "Daily-refreshed NLP arxiv paper digest",
    items: buildFeedItems(keywords, MAIN_FEED_LIMIT),
  });
}
