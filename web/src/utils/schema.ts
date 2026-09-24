import { z } from "astro/zod";

// Structured record the Python pipeline writes (nlp_arxiv_daily/records.py).
// Older data may still hold one-line markdown strings (this repo's no longer
// does); utils/paperRow.ts parses both. `abstract` is optional: the pipeline
// does not store it, and only records written during a few days in 2026-09
// ever had one.
export const paperRecordSchema = z.object({
  date: z.string(),
  title: z.string(),
  authors: z.array(z.string()),
  url: z.string(),
  code: z.string().nullable(),
  abstract: z.string().optional(),
  categories: z.array(z.string()),
});

export const paperValueSchema = z.union([z.string(), paperRecordSchema]);

// Each JSON file (docs/nlp-arxiv-daily-web.json, docs/archive-web/YYYY-MM.json)
// is shaped {keyword: {paper_id: string | record}}.
export const paperBucketSchema = z.record(z.string(), z.record(z.string(), paperValueSchema));
