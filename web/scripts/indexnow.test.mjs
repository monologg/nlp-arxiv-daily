// Unit tests for scripts/indexnow.mjs — run with `pnpm test` (node:test, no
// dependencies). They cover the parts that decide which URLs get submitted;
// the network calls are exercised by `node scripts/indexnow.mjs plan --dry-run`.

import assert from "node:assert/strict";
import { createServer } from "node:http";
import { describe, it } from "node:test";

import {
  MANIFEST_VERSION,
  MAX_URLS_PER_REQUEST,
  canonicalOf,
  chunk,
  diffManifests,
  distPathFor,
  pageFingerprint,
  parseManifest,
  sha256,
  siteRootOf,
  sitemapLocs,
  waitUntilLive,
} from "./indexnow.mjs";

const ROOT = "https://example.org/sub/";

function page({
  title = "Multimodal LLM — 2026-09",
  description = "Papers for Multimodal LLM",
  canonical = `${ROOT}archive/2026-09/multimodal-llm/`,
  main = '<h1>Multimodal LLM</h1><a href="/sub/archive/2026-09/multimodal-llm/2/">Next</a>',
  built = "2026-09-27",
  asset = "index.abc123.css",
} = {}) {
  return `<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="description" content="${description}"><link rel="canonical" href="${canonical}"><title>${title}</title><link rel="stylesheet" href="/sub/_astro/${asset}"><script type="module" src="/sub/_astro/page.${asset}.js"></script></head><body><header><nav><a href="/sub/">Latest</a></nav></header><div class="flex-1"><main class="max-w-3xl">${main}<script>console.log("${asset}")</script><svg viewBox="0 0 24 24"><path d="M0 0"/></svg></main></div><footer><span>Built ${built}</span></footer></body></html>`;
}

describe("pageFingerprint", () => {
  it("is stable for identical pages", () => {
    assert.equal(pageFingerprint(page()), pageFingerprint(page()));
  });

  it("ignores the footer build date and asset hashes", () => {
    assert.equal(
      pageFingerprint(page({ built: "2026-09-27", asset: "a.css" })),
      pageFingerprint(page({ built: "2026-09-28", asset: "b.css" })),
    );
  });

  it("changes when the main text changes", () => {
    assert.notEqual(
      pageFingerprint(page()),
      pageFingerprint(page({ main: "<h1>Multimodal LLM</h1><p>1 new paper</p>" })),
    );
  });

  it("changes when a link target in main changes", () => {
    assert.notEqual(
      pageFingerprint(page({ main: '<a href="https://github.com/x/y">Code</a>' })),
      pageFingerprint(page({ main: '<a href="https://github.com/x/z">Code</a>' })),
    );
  });

  it("changes when the title, description or canonical changes", () => {
    const base = pageFingerprint(page());
    assert.notEqual(base, pageFingerprint(page({ title: "Other" })));
    assert.notEqual(base, pageFingerprint(page({ description: "Other" })));
    assert.notEqual(base, pageFingerprint(page({ canonical: `${ROOT}other/` })));
  });

  it("falls back to the whole body when there is no <main>", () => {
    const html = "<html><head><title>T</title></head><body><p>A</p></body></html>";
    assert.notEqual(
      pageFingerprint(html),
      pageFingerprint(html.replace("<p>A</p>", "<p>B</p>")),
    );
  });
});

describe("canonicalOf", () => {
  it("reads the canonical href", () => {
    assert.equal(canonicalOf(page()), `${ROOT}archive/2026-09/multimodal-llm/`);
  });

  it("returns null without one", () => {
    assert.equal(canonicalOf("<html><head></head></html>"), null);
  });
});

describe("sitemap parsing", () => {
  const index =
    '<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://example.org/sub/sitemap-0.xml</loc></sitemap></sitemapindex>';
  const urlset =
    '<?xml version="1.0" encoding="UTF-8"?><urlset><url><loc>https://example.org/sub/</loc></url><url><loc>https://example.org/sub/archive/</loc><lastmod>2026-09-01</lastmod></url></urlset>';

  it("lists child sitemaps and page URLs", () => {
    assert.deepEqual(sitemapLocs(index, "sitemap"), [`${ROOT}sitemap-0.xml`]);
    assert.deepEqual(sitemapLocs(urlset, "url"), [ROOT, `${ROOT}archive/`]);
  });

  it("takes the site root from the child sitemap's directory", () => {
    assert.equal(siteRootOf(index).href, ROOT);
  });

  it("rejects an index without child sitemaps", () => {
    assert.throws(() => siteRootOf("<sitemapindex></sitemapindex>"), /no <sitemap>/);
  });
});

describe("distPathFor", () => {
  const root = new URL(ROOT);

  it("maps directory URLs to index.html under dist", () => {
    assert.equal(distPathFor(ROOT, root), "index.html");
    assert.equal(
      distPathFor(`${ROOT}archive/2026-09/multimodal-llm/2/`, root),
      "archive/2026-09/multimodal-llm/2/index.html",
    );
  });

  it("keeps file URLs as they are", () => {
    assert.equal(distPathFor(`${ROOT}search.html`, root), "search.html");
  });

  it("rejects URLs outside the site root", () => {
    assert.throws(() => distPathFor("https://example.org/other/", root), /outside/);
    assert.throws(() => distPathFor("https://evil.example/sub/", root), /outside/);
  });

  it("decodes percent-escapes", () => {
    assert.equal(distPathFor(`${ROOT}a%20b/`, root), "a b/index.html");
  });
});

describe("diffManifests", () => {
  it("splits URLs into new, changed and removed", () => {
    const before = new Map([
      ["a", "1"],
      ["b", "2"],
      ["c", "3"],
    ]);
    const after = new Map([
      ["a", "1"],
      ["b", "9"],
      ["d", "4"],
    ]);
    assert.deepEqual(diffManifests(before, after), {
      added: ["d"],
      changed: ["b"],
      removed: ["c"],
    });
  });

  it("treats an unknown (null) baseline hash as unchanged", () => {
    const before = new Map([
      ["a", null],
      ["c", null],
    ]);
    const after = new Map([
      ["a", "1"],
      ["d", "4"],
    ]);
    assert.deepEqual(diffManifests(before, after), {
      added: ["d"],
      changed: [],
      removed: ["c"],
    });
  });
});

describe("parseManifest", () => {
  it("reads url -> hash from a current manifest", () => {
    const text = JSON.stringify({ version: MANIFEST_VERSION, pages: { a: "1" } });
    assert.deepEqual([...parseManifest(text, "m")], [["a", "1"]]);
  });

  it("returns unknown hashes for another manifest version", () => {
    const text = JSON.stringify({ version: MANIFEST_VERSION + 1, pages: { a: "1" } });
    assert.deepEqual([...parseManifest(text, "m")], [["a", null]]);
  });

  it("rejects what isn't a manifest", () => {
    assert.throws(() => parseManifest("<html>", "m"), /not JSON/);
    assert.throws(() => parseManifest('{"version":1,"pages":null}', "m"), /not an IndexNow manifest/);
    assert.throws(() => parseManifest("null", "m"), /not an IndexNow manifest/);
  });
});

describe("chunk", () => {
  it("splits at the IndexNow per-request limit", () => {
    assert.equal(MAX_URLS_PER_REQUEST, 10000);
    const urls = Array.from({ length: 20001 }, (_, i) => String(i));
    assert.deepEqual(
      chunk(urls, MAX_URLS_PER_REQUEST).map((c) => c.length),
      [10000, 10000, 1],
    );
  });

  it("returns no chunks for an empty list", () => {
    assert.deepEqual(chunk([], 10), []);
  });
});

describe("waitUntilLive", () => {
  /** Serve `bodies` in turn (the last one repeats) at /m.json. */
  async function serve(bodies) {
    let hits = 0;
    const server = createServer((req, res) => {
      const body = bodies[Math.min(hits++, bodies.length - 1)];
      if (body === null) {
        res.writeHead(404).end();
      } else {
        res.writeHead(200, { "content-type": "application/json" }).end(body);
      }
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const url = `http://127.0.0.1:${server.address().port}/m.json`;
    return { url, hits: () => hits, close: () => server.close() };
  }

  it("returns once the live manifest is this build's", async (t) => {
    const site = await serve([null, "old", "new"]);
    t.after(site.close);
    const live = await waitUntilLive(
      { manifestUrl: site.url, manifestSha256: sha256("new") },
      { timeoutMs: 5000, pollMs: 10 },
    );
    assert.equal(live, true);
    assert.equal(site.hits(), 3);
  });

  it("gives up after the timeout", async (t) => {
    const site = await serve(["old"]);
    t.after(site.close);
    const live = await waitUntilLive(
      { manifestUrl: site.url, manifestSha256: sha256("new") },
      { timeoutMs: 100, pollMs: 20 },
    );
    assert.equal(live, false);
  });
});
