/* Tell IndexNow engines (Bing, Naver, Yandex, Seznam, Yep; Google does not
 * take part) which pages a deploy added, changed or removed — and only those:
 * IndexNow is for "recently added, updated, or deleted" URLs, not for
 * resubmitting the whole site (https://www.indexnow.org/faq).
 *
 * The sitemap has no <lastmod>, so "changed" comes from a hash of each page's
 * content instead. `plan` hashes every sitemap page into
 * dist/indexnow-manifest.json, which is deployed with the site and becomes the
 * baseline of the next deploy, and diffs it against the live copy. `submit`
 * runs after the deploy, waits until that new manifest is the one being
 * served (so engines don't fetch the old pages), and posts the URLs.
 *
 *   # build job, after `pnpm build` and before the deploy:
 *   node scripts/indexnow.mjs plan --out "$RUNNER_TEMP/indexnow-plan.json"
 *   # after the deploy (INDEXNOW_KEY from the repository variable):
 *   node scripts/indexnow.mjs submit --plan "$RUNNER_TEMP/indexnow-plan.json"
 *   # local check: diff dist/ against the live site, write nothing, submit nothing
 *   node scripts/indexnow.mjs plan --dry-run
 *
 * The key is not a secret: engines verify it by fetching
 * https://<host>/<key>.txt, which must already be served at the host root.
 * Failures exit 1 with an ::error:: annotation; the workflow keeps them from
 * failing the deploy.
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

export const MAX_URLS_PER_REQUEST = 10_000; // https://www.indexnow.org/documentation
export const MANIFEST_NAME = "indexnow-manifest.json";
// Bump when pageFingerprint changes what it hashes: the next deploy then
// treats the old hashes as unknown instead of reporting every page as changed.
export const MANIFEST_VERSION = 1;
const ENDPOINT = "https://api.indexnow.org/indexnow";
// GitHub Pages' CDN caches for `max-age=600` and ignores query strings, so a
// new file can take up to ~10 minutes to show everywhere.
const LIVE_TIMEOUT_MS = 12 * 60 * 1000;
const LIVE_POLL_MS = 15 * 1000;
const ATTEMPTS = 3;
const RETRY_MS = 30 * 1000;

// ---------------------------------------------------------------- page hashing

function attr(tag, name) {
  return tag.match(new RegExp(`\\s${name}\\s*=\\s*"([^"]*)"`, "i"))?.[1] ?? null;
}

function findTag(html, tagName, predicate) {
  for (const [tag] of html.matchAll(new RegExp(`<${tagName}\\b[^>]*>`, "gi"))) {
    if (predicate(tag)) return tag;
  }
  return null;
}

export function canonicalOf(html) {
  const tag = findTag(html, "link", (t) => attr(t, "rel")?.toLowerCase() === "canonical");
  return tag ? attr(tag, "href") : null;
}

function descriptionOf(html) {
  const tag = findTag(html, "meta", (t) => attr(t, "name")?.toLowerCase() === "description");
  return tag ? attr(tag, "content") : null;
}

/** Text and link targets of a fragment, without markup, scripts or styles. */
function visibleText(fragment) {
  return fragment
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style|svg|template|noscript)\b[\s\S]*?<\/\1\s*>/gi, " ")
    .replace(/<a\b[^>]*>/gi, (tag) => ` ${attr(tag, "href") ?? ""} `)
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Hash of what a search engine indexes on the page: title, description,
 * canonical, and the text and links of <main>. The header, the footer (which
 * carries the build date) and asset file names are left out, so a page only
 * counts as changed when its own content does.
 */
export function pageFingerprint(html) {
  const title = html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1].trim() ?? "";
  const main =
    html.match(/<main\b[^>]*>([\s\S]*)<\/main>/i)?.[1] ??
    html.match(/<body\b[^>]*>([\s\S]*)<\/body>/i)?.[1] ??
    html;
  const content = JSON.stringify([title, descriptionOf(html), canonicalOf(html), visibleText(main)]);
  return createHash("sha256").update(content).digest("hex").slice(0, 16);
}

// ------------------------------------------------------------- sitemap and diff

function unescapeXml(text) {
  return text
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&apos;", "'")
    .replaceAll("&amp;", "&");
}

/** <loc> of every <url> (block "url") or <sitemap> (block "sitemap"). */
export function sitemapLocs(xml, block) {
  return [...xml.matchAll(new RegExp(`<${block}>([\\s\\S]*?)</${block}>`, "g"))]
    .map(([, inner]) => inner.match(/<loc>([^<]*)<\/loc>/)?.[1].trim())
    .filter(Boolean)
    .map(unescapeXml);
}

/** The site's root URL: the directory the sitemap index's children live in. */
export function siteRootOf(indexXml) {
  const [first] = sitemapLocs(indexXml, "sitemap");
  if (!first) throw new Error("sitemap index lists no <sitemap>");
  return new URL(".", first);
}

/** Path under dist/ of the file served at `url`. */
export function distPathFor(url, root) {
  const u = new URL(url);
  if (u.origin !== root.origin || !u.pathname.startsWith(root.pathname)) {
    throw new Error(`${url} is outside ${root.href}`);
  }
  let rel = decodeURIComponent(u.pathname.slice(root.pathname.length));
  if (rel === "" || rel.endsWith("/")) rel += "index.html";
  if (path.normalize(rel).startsWith("..")) throw new Error(`${url} is outside ${root.href}`);
  return rel;
}

/**
 * New, changed and removed URLs between two url -> hash maps. A null hash in
 * `before` means "unknown" (baseline from a sitemap, not a manifest): such a
 * URL is never reported as changed.
 */
export function diffManifests(before, after) {
  const added = [];
  const changed = [];
  for (const [url, hash] of after) {
    if (!before.has(url)) added.push(url);
    else if (before.get(url) !== null && before.get(url) !== hash) changed.push(url);
  }
  const removed = [...before.keys()].filter((url) => !after.has(url));
  return { added, changed, removed };
}

export function chunk(list, size) {
  const chunks = [];
  for (let i = 0; i < list.length; i += size) chunks.push(list.slice(i, i + size));
  return chunks;
}

// ------------------------------------------------------------------ CI helpers

class Failure extends Error {}

function annotate(level, message) {
  // ::error:: / ::warning:: show up as annotations on the workflow run.
  console.log(`::${level}::${message}`);
}

function summary(markdown) {
  if (process.env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${markdown}\n`);
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export const sha256 = (text) => createHash("sha256").update(text).digest("hex");

/** fetch with retries on network errors, 429 and 5xx; returns the last response. */
async function request(url, init = {}) {
  const what = `${init.method ?? "GET"} ${url}`;
  for (let attempt = 1; ; attempt++) {
    let res;
    let problem;
    try {
      res = await fetch(url, { ...init, signal: AbortSignal.timeout(30_000) });
      if (res.status !== 429 && res.status < 500) return res;
      problem = `HTTP ${res.status}`;
    } catch (err) {
      problem = err.cause?.message ?? err.message;
    }
    if (attempt === ATTEMPTS) {
      if (res) return res;
      throw new Failure(`${what}: ${problem} (${ATTEMPTS} attempts)`);
    }
    const retryAfter = Number(res?.headers.get("retry-after"));
    const wait = retryAfter > 0 ? Math.min(retryAfter, 120) * 1000 : RETRY_MS;
    console.log(`${what}: ${problem}; retrying in ${wait / 1000}s`);
    await sleep(wait);
  }
}

/** Body of a live URL, or null on 404. */
async function fetchLive(url) {
  const res = await request(url, { headers: { "cache-control": "no-cache" } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Failure(`GET ${url}: HTTP ${res.status}`);
  return res.text();
}

// ------------------------------------------------------------------------ plan

/**
 * url -> hash from a manifest. Hashes from another MANIFEST_VERSION come back
 * as null (unknown), so a changed fingerprint doesn't flag every page once.
 */
export function parseManifest(text, source) {
  let manifest;
  try {
    manifest = JSON.parse(text);
  } catch (err) {
    throw new Failure(`${source} is not JSON: ${err.message}`);
  }
  const { version, pages } = manifest ?? {};
  if (!Number.isInteger(version) || typeof pages !== "object" || pages === null) {
    throw new Failure(`${source} is not an IndexNow manifest`);
  }
  if (version !== MANIFEST_VERSION) {
    annotate(
      "warning",
      `IndexNow: ${source} is manifest version ${version}, not ${MANIFEST_VERSION}; changed pages can't be told apart this time`,
    );
    return new Map(Object.keys(pages).map((url) => [url, null]));
  }
  return new Map(Object.entries(pages));
}

async function liveSitemapUrls(root) {
  const index = await fetchLive(new URL("sitemap-index.xml", root).href);
  if (index === null) return [];
  const urls = [];
  for (const loc of sitemapLocs(index, "sitemap")) {
    const xml = await fetchLive(loc);
    if (xml === null) throw new Failure(`live sitemap index lists ${loc}, which is 404`);
    urls.push(...sitemapLocs(xml, "url"));
  }
  return urls;
}

async function plan({ dist, out, baseline, dryRun }) {
  const read = (rel) => {
    const file = path.join(dist, rel);
    if (!fs.existsSync(file)) throw new Failure(`${file} not found — run \`pnpm build\` first`);
    return fs.readFileSync(file, "utf8");
  };

  const indexXml = read("sitemap-index.xml");
  const root = siteRootOf(indexXml);
  const pages = new Map();
  const miscanonical = [];
  for (const sitemap of sitemapLocs(indexXml, "sitemap")) {
    for (const url of sitemapLocs(read(distPathFor(sitemap, root)), "url")) {
      const html = read(distPathFor(url, root));
      pages.set(url, pageFingerprint(html));
      if (canonicalOf(html) !== url) miscanonical.push(`${url} -> ${canonicalOf(html)}`);
    }
  }
  if (miscanonical.length > 0) {
    annotate(
      "warning",
      `IndexNow: ${miscanonical.length} sitemap pages have a canonical other than their own URL, e.g. ${miscanonical[0]}`,
    );
  }
  const manifestText = `${JSON.stringify({ version: MANIFEST_VERSION, pages: Object.fromEntries(pages) })}\n`;
  // Written before the baseline is fetched, so even when that fails the next
  // deploy still has this build to diff against.
  if (!dryRun) fs.writeFileSync(path.join(dist, MANIFEST_NAME), manifestText);

  const manifestUrl = new URL(MANIFEST_NAME, root).href;
  const source = baseline ?? manifestUrl;
  if (baseline && !fs.existsSync(baseline)) throw new Failure(`--baseline ${baseline} not found`);
  const liveManifest = baseline ? fs.readFileSync(baseline, "utf8") : await fetchLive(manifestUrl);
  let before;
  if (liveManifest !== null) {
    before = parseManifest(liveManifest, source);
  } else {
    annotate(
      "warning",
      `IndexNow: ${manifestUrl} is not live yet (first deploy with IndexNow?), so changed pages can't be told apart this time; only URLs new to or removed from the live sitemap are listed`,
    );
    before = new Map((await liveSitemapUrls(root)).map((url) => [url, null]));
  }

  const { added, changed, removed } = diffManifests(before, pages);
  for (const [label, list] of [
    ["new", added],
    ["changed", changed],
    ["removed", removed],
  ]) {
    for (const url of list) console.log(`${label}\t${url}`);
  }
  const counts = `${added.length} new, ${changed.length} changed, ${removed.length} removed`;
  console.log(
    `IndexNow: ${counts} (${pages.size} URLs in this build's sitemap, baseline ${liveManifest !== null ? source : "live sitemap"})`,
  );
  if (dryRun) {
    console.log(`[dry-run] would submit ${added.length + changed.length + removed.length} URLs; nothing written`);
    return;
  }
  summary(`IndexNow plan: ${counts}.`);
  if (out) {
    const planJson = {
      siteRoot: root.href,
      manifestUrl,
      manifestSha256: sha256(manifestText),
      counts: { new: added.length, changed: changed.length, removed: removed.length },
      urls: [...added, ...changed, ...removed],
    };
    fs.writeFileSync(out, `${JSON.stringify(planJson, null, 2)}\n`);
    console.log(`IndexNow: wrote plan to ${out}`);
  }
}

// ---------------------------------------------------------------------- submit

/** Poll until the live manifest is this build's; false on timeout. */
export async function waitUntilLive(
  { manifestUrl, manifestSha256 },
  { timeoutMs = LIVE_TIMEOUT_MS, pollMs = LIVE_POLL_MS } = {},
) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      const live = await fetchLive(manifestUrl);
      if (live !== null && sha256(live) === manifestSha256) return true;
      console.log(`waiting for the deploy: ${manifestUrl} is still the previous one`);
    } catch (err) {
      console.log(`waiting for the deploy: ${err.message}`);
    }
    if (Date.now() + pollMs > deadline) return false;
    await sleep(pollMs);
  }
}

async function submit({ planFile, dryRun }) {
  const planJson = JSON.parse(fs.readFileSync(planFile, "utf8"));
  const { urls } = planJson;
  if (urls.length === 0) {
    console.log("IndexNow: no new, changed or removed pages; nothing submitted");
    summary("IndexNow: no new, changed or removed pages; nothing submitted.");
    return;
  }

  const key = process.env.INDEXNOW_KEY?.trim();
  if (!key) {
    annotate(
      "warning",
      `IndexNow: the INDEXNOW_KEY repository variable is not set, so ${urls.length} URLs were not submitted`,
    );
    summary(`IndexNow: INDEXNOW_KEY not set; ${urls.length} URLs not submitted.`);
    return;
  }
  // https://www.indexnow.org/documentation: 8-128 of a-z, A-Z, 0-9 and "-".
  if (!/^[A-Za-z0-9-]{8,128}$/.test(key)) {
    throw new Failure("INDEXNOW_KEY must be 8-128 characters of a-z, A-Z, 0-9 and -");
  }

  const root = new URL(planJson.siteRoot);
  const outside = urls.find((url) => new URL(url).host !== root.host);
  if (outside) throw new Failure(`${outside} is not on ${root.host}`);
  const keyLocation = `${root.origin}/${key}.txt`;
  const served = await fetchLive(keyLocation);
  if (served?.trim() !== key) {
    throw new Failure(
      `${keyLocation} ${served === null ? "is 404" : "does not contain the key"}; engines would reject the submission`,
    );
  }

  if (dryRun) {
    console.log(
      `[dry-run] key file ok; would wait for ${planJson.manifestUrl}, then post ${urls.length} URLs for ${root.host} in ${chunk(urls, MAX_URLS_PER_REQUEST).length} request(s)`,
    );
    return;
  }

  if (!(await waitUntilLive(planJson))) {
    // Submit anyway: the next deploy diffs against whatever is live by then,
    // so skipping would drop these URLs for good. An early ping only means an
    // engine may fetch the old page once and come back later.
    annotate(
      "warning",
      `IndexNow: ${planJson.manifestUrl} still isn't this deploy's after ${LIVE_TIMEOUT_MS / 60000} min; submitting anyway`,
    );
  }

  for (const urlList of chunk(urls, MAX_URLS_PER_REQUEST)) {
    const res = await request(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ host: root.host, key, keyLocation, urlList }),
    });
    // 200 = received, 202 = received, key validation pending.
    if (res.status !== 200 && res.status !== 202) {
      throw new Failure(`HTTP ${res.status} ${(await res.text()).slice(0, 500)}`);
    }
    console.log(`IndexNow: submitted ${urlList.length} URLs (HTTP ${res.status})`);
  }
  const { counts } = planJson;
  summary(
    `IndexNow: submitted ${urls.length} URLs — ${counts.new} new, ${counts.changed} changed, ${counts.removed} removed.`,
  );
}

// ------------------------------------------------------------------------ main

async function main() {
  const { positionals, values } = parseArgs({
    allowPositionals: true,
    options: {
      dist: { type: "string", default: "dist" },
      out: { type: "string" },
      baseline: { type: "string" },
      plan: { type: "string" },
      "dry-run": { type: "boolean", default: false },
    },
  });
  const dryRun = values["dry-run"];
  const [command] = positionals;
  if (command === "plan") {
    await plan({ dist: values.dist, out: values.out, baseline: values.baseline, dryRun });
  } else if (command === "submit" && values.plan) {
    await submit({ planFile: values.plan, dryRun });
  } else {
    throw new Failure(
      "usage: indexnow.mjs plan [--out plan.json] [--baseline manifest.json] [--dry-run] | submit --plan plan.json [--dry-run]",
    );
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    await main();
  } catch (err) {
    const message = err instanceof Failure ? err.message : (err.stack ?? String(err));
    annotate("error", `IndexNow: ${message.split("\n")[0]}`);
    if (!(err instanceof Failure)) console.error(message);
    summary(`**IndexNow failed:** ${message.split("\n")[0]}`);
    process.exit(1);
  }
}
