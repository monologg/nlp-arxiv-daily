import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import currentPapers from "../../../docs/nlp-arxiv-daily-web.json";
import { paperBucketSchema } from "../content.config.ts";
import { parsePaperRow } from "../utils/paperRow.ts";

interface FeedItem {
  title: string;
  link: string;
  pubDate: Date;
  description: string;
  customData: string;
}

export async function GET(context: APIContext) {
  const data = paperBucketSchema.parse(currentPapers);

  const items: FeedItem[] = [];
  for (const [keyword, papers] of Object.entries(data)) {
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
  // Newest first.
  items.sort((a, b) => b.pubDate.getTime() - a.pubDate.getTime());

  // The channel <link> should point at the actual home page, which lives
  // under the base path (/nlp-arxiv-daily/) — Astro.site by itself drops it.
  const homeUrl = new URL(import.meta.env.BASE_URL, context.site!).toString();

  return rss({
    title: "NLP Arxiv Daily",
    description: "Daily-refreshed NLP arxiv paper digest",
    site: homeUrl,
    items,
  });
}
