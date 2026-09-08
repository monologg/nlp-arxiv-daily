import { getCollection } from "astro:content";
import currentPapers from "../../../docs/nlp-arxiv-daily-web.json";
import { paperBucketSchema } from "../content.config.ts";
import type { PaperValue } from "./paperRow.ts";

export type PaperBucket = Record<string, Record<string, PaperValue>>;
export type KeywordEntries = Array<[string, Record<string, PaperValue>]>;

export function nonEmptyKeywords(data: PaperBucket): KeywordEntries {
  return Object.entries(data).filter(([, papers]) => Object.keys(papers).length > 0);
}

export interface LatestSnapshot {
  data: PaperBucket;
  keywords: KeywordEntries;
  /** Set when the current-month JSON was empty and we fell back to the
   * newest non-empty archive month. */
  fallbackMonth: string | null;
}

/**
 * The "Latest" dataset: the current-month JSON, or — early in a month before
 * the cron has landed anything — the newest non-empty archive snapshot.
 * Shared by the index page and the BibTeX endpoints so both agree on what
 * "latest" means.
 */
export async function resolveLatest(): Promise<LatestSnapshot> {
  const currentData = paperBucketSchema.parse(currentPapers);
  const currentKeywords = nonEmptyKeywords(currentData);
  if (currentKeywords.length > 0) {
    return { data: currentData, keywords: currentKeywords, fallbackMonth: null };
  }

  const entries = await getCollection("archive");
  const candidates = entries
    .map((e) => ({ id: e.id, data: e.data, keywords: nonEmptyKeywords(e.data) }))
    .filter((c) => c.keywords.length > 0)
    .sort((a, b) => b.id.localeCompare(a.id));

  if (candidates.length === 0) {
    return { data: currentData, keywords: [], fallbackMonth: null };
  }
  const latest = candidates[0];
  return { data: latest.data, keywords: latest.keywords, fallbackMonth: latest.id };
}
