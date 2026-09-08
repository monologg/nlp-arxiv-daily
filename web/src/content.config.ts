import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// Structured record the Python pipeline writes since the format switch
// (nlp_arxiv_daily/records.py). Older rows in the same files are one-line
// markdown strings; utils/paperRow.ts parses both.
export const paperRecordSchema = z.object({
  date: z.string(),
  title: z.string(),
  authors: z.array(z.string()),
  url: z.string(),
  code: z.string().nullable(),
  abstract: z.string(),
  categories: z.array(z.string()),
});

export const paperValueSchema = z.union([z.string(), paperRecordSchema]);

// Each JSON file (docs/nlp-arxiv-daily-web.json, docs/archive-web/YYYY-MM.json)
// is shaped {keyword: {paper_id: string | record}}.
export const paperBucketSchema = z.record(z.string(), z.record(z.string(), paperValueSchema));

const archive = defineCollection({
  loader: glob({
    base: "../docs/archive-web",
    pattern: "*.json",
  }),
  schema: paperBucketSchema,
});

export const collections = { archive };
