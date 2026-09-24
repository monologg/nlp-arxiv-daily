# web

The [Astro](https://astro.build) site behind [monologg.kr/nlp-arxiv-daily](https://monologg.kr/nlp-arxiv-daily). It has no server or database: at build time it reads the JSON the Python pipeline writes — `../docs/nlp-arxiv-daily-web.json` (current month) and `../docs/archive-web/YYYY-MM.json` (earlier months) — and renders static pages, RSS feeds, BibTeX files and OG images. [Pagefind](https://pagefind.app) indexes the result for search.

## Commands

Run from `web/`. Node version: `engines` in `package.json`; pnpm version: `.github/workflows/astro-build.yml`.

| Command                        | Action                                                        |
| :----------------------------- | :------------------------------------------------------------ |
| `pnpm install`                 | Install dependencies                                          |
| `NODE_ENV=production pnpm dev` | Dev server at `http://localhost:4321/<base>/`                 |
| `pnpm build`                   | Build the whole archive into `dist/` and index it for search  |
| `pnpm preview`                 | Serve `dist/` at `http://localhost:4321/<base>/`              |

`<base>` is the `base` in `astro.config.mjs` (`nlp-arxiv-daily` here). `pnpm dev` needs `NODE_ENV=production`: `site` and `base` are set only in production, and without a `site` every page fails with `Invalid URL`. `astro build` and `astro preview` run in production mode on their own.

## Build-time settings

Defaults and minimums are in `src/utils/papers.ts`.

| Variable                    | Effect                                                                   |
| :-------------------------- | :----------------------------------------------------------------------- |
| `DOCS_DIR`                  | Where to read the JSON from (default `../docs`, then `./docs`); the directory must contain `nlp-arxiv-daily-web.json` or `archive-web/` |
| `PUBLIC_PAGE_SIZE`          | Papers per page on the keyword × month archive pages                     |
| `PUBLIC_LATEST_PER_KEYWORD` | Papers per keyword on the Latest page before the "View all" link         |
| `PUBLIC_ADSENSE_CLIENT`     | AdSense publisher ID; when unset, no ad script is added                  |

## Things that break quietly

- Month files are read one at a time through `src/utils/papers.ts`, not through a content collection, which would hold the whole archive in memory for the entire build.
- Search indexes the keyword × month pages, not single papers: each result is a whole page of cards, titled after the last card on it (every card sets `data-pagefind-meta="title"` and Pagefind keeps one per page). A paper filed under several keywords is found on each of those pages. Latest, the month index and the archive index carry `data-pagefind-ignore="all"` so they add no further copies; a new page that lists papers needs it too.
