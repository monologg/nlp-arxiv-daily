import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { parsePaperRow } from "./paperRow.ts";
import type { KeywordEntries } from "./papers.ts";

export interface FeedItem {
  title: string;
  link: string;
  pubDate: Date;
  description: string;
  customData: string;
}

/**
 * Flatten keyword buckets into RSS items, newest first. A paper matched by
 * several keywords appears once per keyword in the main feed — readers
 * de-duplicate on <link>, and the <category> tells them which keyword hit.
 */
export function buildFeedItems(buckets: KeywordEntries): FeedItem[] {
  const items: FeedItem[] = [];
  for (const [keyword, papers] of buckets) {
    for (const [paperId, row] of Object.entries(papers)) {
      const parsed = parsePaperRow(row);
      if (!parsed) continue;
      items.push({
        title: parsed.title,
        link: parsed.paperUrl,
        pubDate: new Date(parsed.date),
        description: `${parsed.firstAuthor} et al. — arxiv:${paperId} — ${keyword}`,
        customData: `<category>${keyword}</category>`,
      });
    }
  }
  items.sort((a, b) => b.pubDate.getTime() - a.pubDate.getTime());
  return items;
}

export function feedResponse(
  context: APIContext,
  opts: { title: string; description: string; items: FeedItem[] },
) {
  // The channel <link> should point at the actual home page, which lives
  // under the base path (/nlp-arxiv-daily/) — Astro.site by itself drops it.
  const homeUrl = new URL(import.meta.env.BASE_URL, context.site!).toString();
  return rss({ title: opts.title, description: opts.description, site: homeUrl, items: opts.items });
}
