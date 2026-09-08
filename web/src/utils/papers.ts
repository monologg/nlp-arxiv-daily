import fs from "node:fs";
import path from "node:path";
import { paperBucketSchema } from "./schema.ts";
import { parsePaper, sortPapersDesc, type PaperValue } from "./paperRow.ts";

export type PaperBucket = Record<string, Record<string, PaperValue>>;
export type KeywordEntries = Array<[string, Record<string, PaperValue>]>;

/** Papers per page on the keyword month pages (arxiv's own listings use 50–500). */
export const PAGE_SIZE = Math.max(25, Number(import.meta.env.PUBLIC_PAGE_SIZE ?? 200) || 200);
/** Newest papers shown per keyword on the Latest page before the "show all" link. */
export const LATEST_PER_KEYWORD = Math.max(5, Number(import.meta.env.PUBLIC_LATEST_PER_KEYWORD ?? 50) || 50);

// docs/ lives one level above web/. Modules are bundled into dist/ at build
// time, so import.meta.url is useless here; resolve from the working
// directory instead (astro runs from web/ locally and in CI, but accept the
// repo root too) or from an explicit DOCS_DIR.
function findDocsDir(): string {
  const candidates = [
    process.env.DOCS_DIR,
    path.resolve(process.cwd(), "../docs"),
    path.resolve(process.cwd(), "docs"),
  ].filter((c): c is string => Boolean(c));
  const hit = candidates.find((c) => fs.existsSync(path.join(c, "archive-web")));
  if (!hit) throw new Error(`docs/ directory not found; tried ${candidates.join(", ")}`);
  return hit;
}
const DOCS_DIR = findDocsDir();
const CURRENT_PATH = path.join(DOCS_DIR, "nlp-arxiv-daily-web.json");
const ARCHIVE_DIR = path.join(DOCS_DIR, "archive-web");

/**
 * The month files are large (a full month is ~10k rows) and there are 100+
 * of them, so they are NOT loaded through a content collection — Astro would
 * hold every file in memory for the whole build. Instead each page reads the
 * one month it needs, through a one-entry cache: pages are built in
 * getStaticPaths order, month by month, so consecutive renders hit the cache.
 */
let cache: { id: string; data: PaperBucket } | null = null;

function readBucket(file: string): PaperBucket {
  const raw = fs.readFileSync(file, "utf8");
  return paperBucketSchema.parse(raw.trim() ? JSON.parse(raw) : {});
}

export function nonEmptyKeywords(data: PaperBucket): KeywordEntries {
  return Object.entries(data).filter(([, papers]) => Object.keys(papers).length > 0);
}

export function totalRows(data: PaperBucket): number {
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

let currentIdMemo: string | null | undefined;
/** Id of the live current month (from the main JSON), or null if empty. */
export function getCurrentMonthId(): string | null {
  if (currentIdMemo === undefined) currentIdMemo = currentMonthId(readBucket(CURRENT_PATH));
  return currentIdMemo;
}

/**
 * Every month with a page: archive snapshots plus the live current month
 * (not in the archive dir until the month rolls over). Newest first.
 * Cheap — reads directory names, not file contents.
 */
export function listMonths(): string[] {
  const ids = new Set(
    fs
      .readdirSync(ARCHIVE_DIR)
      .filter((n) => /^\d{4}-\d{2}\.json$/.test(n))
      .map((n) => n.replace(/\.json$/, "")),
  );
  const current = getCurrentMonthId();
  if (current) ids.add(current);
  return Array.from(ids).sort().reverse();
}

export function isCurrentMonth(id: string): boolean {
  return id === getCurrentMonthId();
}

/** Load one month's bucket (cached for the most recent id). */
export function loadMonth(id: string): PaperBucket {
  if (cache?.id === id) return cache.data;
  const file = isCurrentMonth(id) ? CURRENT_PATH : path.join(ARCHIVE_DIR, `${id}.json`);
  const data = fs.existsSync(file) ? readBucket(file) : {};
  cache = { id, data };
  return data;
}

export interface KeywordStat {
  keyword: string;
  count: number;
  pages: number;
}

/** Per-keyword counts for a month, in file (= config.yaml) order. */
export function keywordStats(id: string): KeywordStat[] {
  return nonEmptyKeywords(loadMonth(id)).map(([keyword, papers]) => {
    const count = Object.keys(papers).length;
    return { keyword, count, pages: Math.ceil(count / PAGE_SIZE) };
  });
}

/** One page (1-based) of a keyword's papers, newest first. */
export function keywordPage(id: string, keyword: string, page: number): Array<[string, PaperValue]> {
  const papers = loadMonth(id)[keyword] ?? {};
  const start = (page - 1) * PAGE_SIZE;
  return sortPapersDesc(papers).slice(start, start + PAGE_SIZE);
}

export interface LatestSnapshot {
  data: PaperBucket;
  keywords: KeywordEntries;
  /** Month id the data belongs to (the newest non-empty month). */
  monthId: string | null;
  /** Set when the current-month JSON was empty and we fell back to the
   * newest non-empty archive month. */
  fallbackMonth: string | null;
}

/**
 * The "Latest" dataset: the current-month JSON, or — early in a month before
 * the cron has landed anything — the newest non-empty archive snapshot.
 * Shared by the index page, its .bib files and the RSS feeds.
 */
export function resolveLatest(): LatestSnapshot {
  const current = getCurrentMonthId();
  if (current) {
    const data = loadMonth(current);
    return { data, keywords: nonEmptyKeywords(data), monthId: current, fallbackMonth: null };
  }
  for (const id of listMonths()) {
    const data = loadMonth(id);
    const keywords = nonEmptyKeywords(data);
    if (keywords.length > 0) return { data, keywords, monthId: id, fallbackMonth: id };
  }
  return { data: {}, keywords: [], monthId: null, fallbackMonth: null };
}

/** Newest `limit` papers of a bucket, plus how many were left out. */
export function newest(
  papers: Record<string, PaperValue>,
  limit: number,
): { shown: Array<[string, PaperValue]>; hidden: number } {
  const all = sortPapersDesc(papers);
  return { shown: all.slice(0, limit), hidden: Math.max(0, all.length - limit) };
}

export { parsePaper };
