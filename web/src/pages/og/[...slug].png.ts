import { OGImageRoute } from "astro-og-canvas";
import { getCollection } from "astro:content";
import currentPapers from "../../../../docs/nlp-arxiv-daily-web.json";
import { paperBucketSchema } from "../../content.config.ts";

interface OgPage {
  title: string;
  description: string;
}

const today = new Date().toISOString().slice(0, 10);

const pages: Record<string, OgPage> = {
  index: {
    title: "NLP Arxiv Daily",
    description: `Updated ${today}`,
  },
  archive: {
    title: "Archive",
    description: "Monthly snapshots — NLP Arxiv Daily",
  },
};

// Add per-month archive cards.
const archiveEntries = await getCollection("archive");
for (const entry of archiveEntries) {
  const data = paperBucketSchema.parse(entry.data);
  const total = Object.values(data).reduce(
    (sum, papers) => sum + Object.keys(papers).length,
    0,
  );
  pages[`archive/${entry.id}`] = {
    title: entry.id,
    description: `${total} papers — NLP Arxiv Daily`,
  };
}

// Current month also gets a "live" count.
{
  const data = paperBucketSchema.parse(currentPapers);
  const total = Object.values(data).reduce(
    (sum, papers) => sum + Object.keys(papers).length,
    0,
  );
  pages.index.description = `${total} papers · Updated ${today}`;
}

export const prerender = true;

// OGImageRoute returns a Promise — must await at module top.
export const { getStaticPaths, GET } = await OGImageRoute({
  param: "slug",
  pages,
  // Default getSlug appends ".png"; route file `[...slug].png.ts` already
  // owns that extension, so return the path verbatim or we'd get `.png.png`.
  getSlug: (path) => path,
  getImageOptions: (_path, page: OgPage) => ({
    title: page.title,
    description: page.description,
    bgGradient: [
      [22, 23, 33],
      [40, 42, 60],
    ],
    border: { color: [120, 120, 220], width: 6, side: "block-start" },
    padding: 80,
    font: {
      title: { size: 80, weight: "Bold", color: [255, 255, 255], lineHeight: 1.2 },
      description: { size: 36, color: [180, 180, 200], lineHeight: 1.4 },
    },
  }),
});
