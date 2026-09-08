import { getCollection } from "astro:content";
import currentPapers from "../../../docs/nlp-arxiv-daily-web.json";
import { paperBucketSchema } from "../content.config.ts";
import { parsePaper, type PaperValue } from "./paperRow.ts";

export type PaperBucket = Record<string, Record<string, PaperValue>>;
export type KeywordEntries = Array<[string, Record<string, PaperValue>]>;

/** Days of papers the Latest page shows. Forks can override at build time
 * with PUBLIC_LATEST_WINDOW_DAYS; the full month lives under /archive/. */
export const LATEST_WINDOW_DAYS = Math.max(1, Number(import.meta.env.PUBLIC_LATEST_WINDOW_DAYS ?? 7) || 7);

export function nonEmptyKeywords(data: PaperBucket): KeywordEntries {
  return Object.entries(data).filter(([, papers]) => Object.keys(papers).length > 0);
}

function totalRows(data: PaperBucket): number {
  return Object.values(data).reduce((sum, papers) => sum + Object.keys(papers).length, 0);
}

/**
 * "YYYY-MM" for the current-month JSON, derived from its arxiv ids (the
 * pipeline buckets that file by id prefix, so the newest prefix is the
 * month). Null when the file is empty.
 */
export function currentMonthId(data: PaperBucket): string | null {
  let best: string | null = null;
  for (const papers of Object.values(data)) {
    for (const id of Object.keys(papers)) {
      const m = id.match(/^(\d{2})(\d{2})\./);
      if (!m) continue;
      const ym = `20${m[1]}-${m[2]}`;
      if (best === null || ym > best) best = ym;
    }
  }
  return best;
}

export interface MonthEntry {
  id: string; // "YYYY-MM"
  data: PaperBucket;
  /** True for the live current-month file (rebuilt every 12h). */
  current: boolean;
}

/**
 * Every month we can render a page for: the archive snapshots plus the
 * current-month JSON (which is not in the archive until the month rolls
 * over). Newest first. Empty months are dropped.
 */
export async function allMonths(): Promise<MonthEntry[]> {
  const entries = await getCollection("archive");
  const months: MonthEntry[] = entries
    .filter((e) => totalRows(e.data) > 0)
    .map((e) => ({ id: e.id, data: e.data, current: false }));

  const currentData = paperBucketSchema.parse(currentPapers);
  const currentId = currentMonthId(currentData);
  if (currentId && !months.some((m) => m.id === currentId)) {
    months.push({ id: currentId, data: currentData, current: true });
  }
  return months.sort((a, b) => b.id.localeCompare(a.id));
}

export interface LatestSnapshot {
  data: PaperBucket;
  keywords: KeywordEntries;
  /** Set when the current-month JSON was empty and we fell back to the
   * newest non-empty archive month. */
  fallbackMonth: string | null;
}

/**
 * The newest whole month: the current-month JSON, or — early in a month
 * before the cron has landed anything — the newest non-empty archive
 * snapshot. Used by the RSS feeds, which want more history than the
 * Latest page's day window.
 */
export async function resolveLatest(): Promise<LatestSnapshot> {
  const currentData = paperBucketSchema.parse(currentPapers);
  const currentKeywords = nonEmptyKeywords(currentData);
  if (currentKeywords.length > 0) {
    return { data: currentData, keywords: currentKeywords, fallbackMonth: null };
  }
  const months = await allMonths();
  if (months.length === 0) return { data: currentData, keywords: [], fallbackMonth: null };
  return { data: months[0].data, keywords: nonEmptyKeywords(months[0].data), fallbackMonth: months[0].id };
}

export interface RecentSnapshot {
  keywords: KeywordEntries;
  windowDays: number;
  /** ISO date (inclusive) the window starts at. */
  since: string;
  /** Month page that holds the full list the window was cut from. */
  monthId: string | null;
  /** True when the window held nothing and the whole newest month is shown. */
  widened: boolean;
}

/**
 * The Latest page dataset: papers submitted in the last `days` days, across
 * the newest two months (so the window survives a month boundary). Keyword
 * order follows the current-month file, i.e. config.yaml. If the window is
 * empty (arxiv holiday, cron outage) the newest month is shown whole.
 */
export async function resolveRecent(days: number = LATEST_WINDOW_DAYS): Promise<RecentSnapshot> {
  const months = await allMonths();
  if (months.length === 0) return { keywords: [], windowDays: days, since: "", monthId: null, widened: false };

  const sinceDate = new Date();
  sinceDate.setUTCDate(sinceDate.getUTCDate() - (days - 1));
  const since = sinceDate.toISOString().slice(0, 10);

  const merged: PaperBucket = {};
  for (const month of months.slice(0, 2)) {
    for (const [keyword, papers] of Object.entries(month.data)) {
      const bucket = (merged[keyword] ??= {});
      for (const [id, value] of Object.entries(papers)) {
        if (id in bucket) continue;
        const parsed = parsePaper(value);
        if (parsed && parsed.date >= since) bucket[id] = value;
      }
    }
  }

  const keywords = nonEmptyKeywords(merged);
  if (keywords.length > 0) {
    return { keywords, windowDays: days, since, monthId: months[0].id, widened: false };
  }
  return {
    keywords: nonEmptyKeywords(months[0].data),
    windowDays: days,
    since,
    monthId: months[0].id,
    widened: true,
  };
}
