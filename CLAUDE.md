# CLAUDE.md

Notes for contributors and coding agents. [README.md](README.md) explains the project and how to fork it; this file lists the rules that break things silently when ignored.

## Layout

- `nlp_arxiv_daily/` — Python pipeline: arXiv fetch, HuggingFace Papers code-link lookup, JSON storage. `uv run python -m nlp_arxiv_daily --help` lists the subcommands.
- `web/` — Astro static site that reads the JSON at build time ([web/README.md](web/README.md)).
- `docs/nlp-arxiv-daily-web.json` (current month) and `docs/archive-web/YYYY-MM.json` (earlier months) — the data, `{keyword: {arxiv_id: record}}`.
- `config.yaml` — keywords and their filter phrases. Keyword order there is section order on the site.

## Data

- The cron (`.github/workflows/nlp-arxiv-daily.yml`) commits data to `master` on the schedule in that workflow: the current-month file and, in the first days of a month, the previous month's file too (`daily_lookback_days` in `config.yaml`). A data branch that touches those files needs a rebase right before merge. Each file is a single line of JSON, so on a conflict take master's copy and re-run the backfill for that month (it is idempotent) instead of merging by hand.
- Rows are filed by the arXiv id's `YYMM` prefix, not by their `date` field.
- Writes only add or overwrite rows; nothing is ever deleted. Narrowing a filter or dropping a keyword leaves the old rows in place, and every keyword present in the JSON is rendered whether or not it is still in `config.yaml`. Remove such rows by hand.
- Changing the query builder (`load_config` in `core.py`) or a keyword's filters does not touch months already stored under the old query: re-fetch every affected month × keyword, plus the manual cleanup above if the query got narrower.
- Code links are looked up once per paper and never re-checked. A failed HuggingFace lookup falls back to a GitHub URL in the abstract, and without one is stored as `code: null`, the same as "no repo"; `recheck-code-links --from-log <log>` repairs those.
- Abstracts are fetched but neither stored nor rendered — they were most of the data size. Don't add them back to the JSON or the cards.
- The Latest page covers the whole current month on purpose (newest N per keyword, `PUBLIC_LATEST_PER_KEYWORD` in `web/src/utils/papers.ts`, then "View all"). A rolling 7-day window was tried in #73 and reverted in #75.

## Backfills

- Run them locally, not in GitHub Actions: a GitHub-hosted job is stopped after 6 hours, and a backfill across many months and keywords can run longer.
- Pass `--delay-seconds 15`, split the work with `--keywords` and a few months per run, and add `--window-days 7` for keywords that log `cap hit`.
- A keyword × window that still fails after retries is only logged as `BACKFILL skip`, and the run continues. Grep the log for it and re-run those.
- Logs go to stderr only. Capture them with `2>&1 | tee run.log` so `recheck-code-links --from-log run.log` can repair failed HuggingFace lookups.
- Data PRs: branch `data/backfill-<range>`, title `data: backfill <range> …`. A one-line JSON diff is unreadable, so state the months touched and rows added or removed in the description.

## Checks and CI

- Data-only PRs trigger no CI: `astro-build` runs on PRs only for `web/**`, and `test` / `check-lint` ignore `docs/`. Build the site locally before merging (`cd web && pnpm build`). Merging data into `master` builds and deploys the site.
- `make test` runs the unit tests with the coverage gate in `pyproject.toml`. `make style` fixes lint and formatting, `make quality` only checks (CI runs it with `make check-lock`).
- `pnpm dev` needs `NODE_ENV=production`; see [web/README.md](web/README.md).
- Unit tests fake arXiv and HuggingFace. `make test-integration` calls the real APIs, but only through the older top-N path (`get_daily_papers` / `fetch_papers`), not the date-window path the cron uses, and it currently fails on its `abstract` assertion. The next daily cron run is the first real test of a fetcher change — check it.

## Commits and PRs

- English, with conventional-style prefixes as in history (`feat`, `fix`, `refactor`, `docs`, `ci`, `test`, `chore`, `data`; optional scope, e.g. `fix(backfill):`).
- Self-contained: the message or description says what changed and why. Reference only this repo's public issues and PRs.
