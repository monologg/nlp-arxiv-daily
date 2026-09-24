<div align="center">

# 📚 NLP Arxiv Daily

**Automatically tracked NLP & LLM papers from arXiv — updated every 12 hours.**

[![Website](https://img.shields.io/badge/website-monologg.kr/nlp--arxiv--daily-2563eb?style=for-the-badge)](https://monologg.kr/nlp-arxiv-daily)
[![RSS](https://img.shields.io/badge/RSS-feed-orange?style=for-the-badge&logo=rss)](https://monologg.kr/nlp-arxiv-daily/rss.xml)

[![Daily update](https://github.com/monologg/nlp-arxiv-daily/actions/workflows/nlp-arxiv-daily.yml/badge.svg)](https://github.com/monologg/nlp-arxiv-daily/actions/workflows/nlp-arxiv-daily.yml)
[![Astro build](https://github.com/monologg/nlp-arxiv-daily/actions/workflows/astro-build.yml/badge.svg)](https://github.com/monologg/nlp-arxiv-daily/actions/workflows/astro-build.yml)

### 👉 [**Browse papers on the website →**](https://monologg.kr/nlp-arxiv-daily)

<a href="https://monologg.kr/nlp-arxiv-daily">
  <img src="docs/images/hero.png" alt="NLP Arxiv Daily — website screenshot" width="800" />
</a>

</div>

---

## Features

- 🔎 **Search** across the archive (powered by [Pagefind](https://pagefind.app)) — matches paper titles, up to three authors and dates, not abstracts; each result is a keyword × month page of papers rather than a single paper
- 🏷️ **Keyword tabs** — NLP, LLM, RAG, Reasoning, Multimodal LLM, Long Context, Code LLM, …
- 🗓️ **Monthly archives** back to January 2014 (LLM-era keywords from October 2022) — one page per keyword and month, 200 papers a page, like arXiv's own listings
- 📡 **[RSS feed](https://monologg.kr/nlp-arxiv-daily/rss.xml)** for your reader of choice — plus one feed per keyword (e.g. [`/rss/rag.xml`](https://monologg.kr/nlp-arxiv-daily/rss/rag.xml), `/rss/llm-agent.xml`)
- 📥 **BibTeX export** — per paper (copy button), per keyword, or the whole page / month as one `.bib` file (e.g. [`/bibtex/all.bib`](https://monologg.kr/nlp-arxiv-daily/bibtex/all.bib), `/bibtex/rag.bib`, `/archive/2026-08/all.bib`)
- 🗂️ **Zotero-ready** — every list page embeds [COinS](https://en.wikipedia.org/wiki/COinS) metadata, so the Zotero connector can save all papers on a page in one click (as Preprint items with DOI, URL, and the keyword as a tag)
- 🌓 Light/dark theme, mobile-friendly

## How it works

```
arXiv API ──────────► fetcher ──► JSON snapshots ──► Astro static site ──► GitHub Pages
                         ▲              │
HuggingFace Papers ──────┘              └──► docs/nlp-arxiv-daily-web.json + docs/archive-web/*.json
(code links)
```

A GitHub Actions cron runs every 12 hours: for each keyword it fetches every submission from the last 7 days (idempotent merge, so re-sightings are free), stores the results in the monthly JSON archives, then triggers an Astro rebuild and deploy. A paper seen for the first time gets one [HuggingFace Papers](https://huggingface.co/papers) lookup for its code repository (falling back to a GitHub URL in the abstract); the result is stored and not looked up again.

The current month lives in `docs/nlp-arxiv-daily-web.json`, earlier months in `docs/archive-web/YYYY-MM.json`. Papers are filed by the `YYMM` prefix of their arXiv id.

Each JSON file is `{keyword: {arxiv_id: paper}}`, where `paper` is a record like:

```json
{
  "date": "2026-09-07",
  "title": "…",
  "authors": ["Ada Lovelace", "Alan Turing"],
  "url": "http://arxiv.org/abs/2609.05339v1",
  "code": "https://github.com/x/y",
  "categories": ["cs.CL", "cs.IR"]
}
```

`date` is the arXiv submission date, and `code` is `null` when no repository was found (or the lookup failed, see step 7 below). Abstracts are fetched but not stored — they were most of the file size and the site doesn't show them. The JSON files are stable and safe to consume directly if you want the data without the website.

Code lives in `nlp_arxiv_daily/` (Python pipeline) and `web/` (Astro site, see [`web/README.md`](web/README.md)).

## 🍴 Fork & make it yours

Want a daily tracker for *your* keywords (vision, RecSys, robotics, your own niche)? Fork this repo, set your keywords in `config.yaml`, then point the site at your own URL and name.

### 1. Fork the repo

Click **Fork** on GitHub. The fork comes with all of this repo's data — every paper collected since 2014 (see step 3 to start empty).

### 2. Edit `config.yaml`

Replace the `keywords` block with whatever you want to track, and leave the other keys in place (`user_name` and `repo_name` only matter when `publish_readme` is on, but the pipeline still reads them):

```yaml
daily_lookback_days: 7     # each run re-scans the last N days per keyword
max_results: 1500          # safety cap per keyword per run (not a target)
publish_gitpage: True      # keep True so the website still builds

keywords:
  "Recommender Systems":
    filters: ["Recommender System", "Sequential Recommendation", "Collaborative Filtering"]

  "Graph Neural Networks":
    filters: ["Graph Neural Network", "GNN", "Graph Transformer"]

  "Diffusion":
    filters: ["Diffusion Model", "Score-Based Generative", "DDPM"]
```

Each `filters` entry is a plain word or phrase, not an arXiv query: the pipeline prefixes every entry with `all:` (match anywhere in the paper's metadata, abstract included), quotes multi-word entries, and ORs them together. arXiv query syntax inside an entry (`ti:`, `cat:cs.CL`, `AND`) does not work. Section order on the site follows the order in this file.

> 💡 **Tip:** start with 5–8 keywords. Too many filters means heavy arXiv traffic and slower runs.

### 3. Start from empty data (recommended)

The pipeline only ever adds papers. Everything your fork inherited stays in the JSON — including keywords you removed from `config.yaml`, which keep showing up on the site. To start clean:

```bash
rm docs/archive-web/*.json
touch docs/archive-web/.gitkeep             # the site build needs this directory to exist
echo '{}' > docs/nlp-arxiv-daily-web.json
```

Commit the result. The first daily run then collects the last `daily_lookback_days` days; step 6 fills in older months.

### 4. Update site identity

- `web/astro.config.mjs` — set `site` and `base` to where GitHub Pages serves your fork. Usually that is `https://<user>.github.io` and `/<repo>`. If your `<user>.github.io` site has a custom domain, project sites live under it: `https://<that-domain>` and `/<repo>` (this repo's case). If the fork itself gets a custom domain, use that domain and `/`. Both settings apply to production builds only.
- `web/public/CNAME` — delete it. Pages deploys from GitHub Actions ignore this file; set a custom domain under **Settings → Pages** instead.
- The site name and the GitHub link are hard-coded across `web/src` (header, footer, page titles, RSS, OG images, BibTeX headers, the default description in `Layout.astro`). `grep -rniE "nlp arxiv|monologg" web/src` lists every place.
- `README.md` — the badges, hero image, website links and feature list all describe this repo.
- Optional: the commit author name and email of the daily run are set at the top of `.github/workflows/nlp-arxiv-daily.yml`.

### 5. Enable Actions & Pages

- **Actions** tab: enable workflows (GitHub turns them off in forks). Scheduled workflows in a fork start out disabled, so if **Run Arxiv Papers Daily** is listed as disabled, select it and click **Enable workflow**
- **Settings → Actions → General**: allow read/write permissions for workflows (the daily run commits the JSON back)
- **Settings → Pages**: source = "GitHub Actions"
- Run the **Run Arxiv Papers Daily** workflow once manually. When it succeeds it starts **Astro Build & Deploy** by itself, and both then run on the workflow's schedule

### 6. (Optional) Backfill historical months

```bash
uv run python -m nlp_arxiv_daily backfill --start 2024-01 --end 2025-12 --delay-seconds 15 2>&1 | tee run.log
```

Run it on your own machine, not in GitHub Actions: a job on a GitHub-hosted runner is stopped after [6 hours](https://docs.github.com/en/actions/reference/limits), and a backfill across many months and keywords can take longer — every arXiv request waits `--delay-seconds`, and every new paper gets a HuggingFace lookup. The log goes to stderr, so the `tee` above is what keeps it for step 7. When it finishes, commit the updated JSON and push it to `master`; that push rebuilds and redeploys the site.

**Keywords are not era-neutral.** In this repo, the LLM-era tags (`LLM Agent`, `LLM Efficiency`,
`Code LLM`, …) were added in 2026-04 to follow post-ChatGPT work, and their
filters are ordinary words elsewhere: `Autonomous Agent` and `AI Agent` are
1990s multi-agent-systems vocabulary, `Quantization` is signal processing,
`LoRA` is a radio protocol, `Code Generation` is a compiler term. Backfilling
them into the pre-2022 years fills the archive with unrelated papers — a 2016
`LLM Agent` query returned work on kinetic wealth distribution and DNS
tunneling. History before 2022-10 is therefore covered by the era-neutral NLP
keywords only (`NLP`, `Question Answering`, `Knowledge Graph`,
`Text Classification`, `Information Extraction`, `Named Entity Recognition`,
`Sentiment Analysis`, `Multilingual NLP`, `Medical NLP`, `Legal NLP`); the
LLM-era tags start where the keyword did. Check your own keywords the same way
before backfilling far back.

Idempotent — safe to re-run. Run it in chunks (`--keywords "A,B,C"`, a few months at a time): arXiv rate-limits aggressively. `--delay-seconds` applies between every request. 15s has completed long runs without a 429, while 10s earned a 429 (and a ~40 minute IP throttle) about an hour in — but throttling varies from day to day, so watch the log. A query that still fails after its retries is logged as `BACKFILL skip` and the run moves on; re-run those months and keywords. Each keyword × month query returns at most `--max-results` papers (the default matches the per-call maximum in [arXiv's API manual](https://info.arxiv.org/help/api/user-manual.html)), so a busier keyword gets cut off; add `--window-days 7` to query the month in weekly windows, and watch the log for `cap hit` if a window still overflows.

If you later change a keyword's filters or drop a keyword, stored months keep what the old setup matched: backfill the keyword again to add what the new filters match, and delete rows from the JSON by hand if the filters got narrower or the keyword is gone.

### 7. (Optional) Repair code links after a throttled run

A HuggingFace Papers lookup that fails is stored as `code: null` (unless the
abstract contains a GitHub URL, which is stored instead), which is
indistinguishable from "this paper has no repo" — and the paper then counts as
known, so no later fetch re-asks. Feed the run's log back in to repair them:

```bash
uv run python -m nlp_arxiv_daily recheck-code-links --from-log run.log --dry-run
uv run python -m nlp_arxiv_daily recheck-code-links --from-log run.log
```

It scrapes `HF Papers lookup failed for <id>` lines (or takes `--ids a,b,c`),
re-asks HuggingFace, and fills in only the rows still missing a link.

### 8. (Optional) Serve AdSense ads

The layout injects the AdSense script only when `PUBLIC_ADSENSE_CLIENT` is set at build time. Add a repository variable (**Settings → Secrets and variables → Actions → Variables**) named `ADSENSE_CLIENT` with your publisher ID (e.g. `ca-pub-XXXXXXXXXXXXXXXX`) — the build workflow passes it through. Without it the site builds ad-free.

## Local development

Requires Python 3.13 (see `requires-python` in `pyproject.toml`) and Node (see `engines` in `web/package.json`). The repo uses [`uv`](https://docs.astral.sh/uv/) and [`pnpm`](https://pnpm.io/).

```bash
# pipeline
make set-dev                                # install dependencies
uv run python -m nlp_arxiv_daily run        # the daily fetch (arXiv + HuggingFace) into docs/
make test                                   # unit tests + the coverage gate in pyproject.toml
make style                                  # ruff fix + format
make quality                                # ruff lint + format check, as CI runs it

# website
cd web
pnpm install
NODE_ENV=production pnpm dev                # http://localhost:4321/<base>/
pnpm build && pnpm preview
```

`<base>` is the `base` in `web/astro.config.mjs` (`nlp-arxiv-daily` here). `pnpm dev` needs `NODE_ENV=production`; [`web/README.md`](web/README.md) explains why and lists the build-time settings.

## Reference

This project is a fork-in-spirit of **[Vincentqyw/cv-arxiv-daily](https://github.com/Vincentqyw/cv-arxiv-daily)** — the original "arxiv-daily" pattern for computer vision. Huge thanks to that repo for the idea and the original `config.yaml`/keyword-filter design.

What's different here:
- NLP/LLM keyword set instead of CV
- JSON-first pipeline (no giant markdown tables in the repo)
- Astro static site with Pagefind search, RSS, OG images
- One JSON file per month; the site build reads them one month at a time
