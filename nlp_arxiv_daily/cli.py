"""CLI subcommand dispatch for the nlp_arxiv_daily pipeline.

Four subcommands:
- `fetch`    — query arxiv per keyword, persist current/archive JSON splits.
- `render`   — read the persisted JSON, write README/gitpage/archive markdown.
- `run`      — fetch then render (this is what the cron workflow calls).
- `backfill` — date-range fetch (across many months) merged into the archive.

JSON is the boundary between fetch and render, so the two subcommands can
also be run independently — useful for backfills and golden-output testing.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from collections.abc import Iterator

from nlp_arxiv_daily.core import get_daily_papers, load_config, papers_to_legacy_rows
from nlp_arxiv_daily.fetcher import BACKFILL_DEFAULT_MAX_RESULTS, fetch_papers_in_range
from nlp_arxiv_daily.renderer import json_to_md, render_archive_pages
from nlp_arxiv_daily.storage import write_papers_split


def cmd_fetch(config: dict) -> None:
    """Query arxiv for every keyword in `config["kv"]`, persist JSON splits."""
    keywords = config["kv"]
    max_results = config["max_results"]

    data_collector = []
    data_collector_web = []

    logging.info("GET daily papers begin")
    for topic, keyword in keywords.items():
        logging.info(f"Keyword: {topic}")
        data, data_web = get_daily_papers(topic, query=keyword, max_results=max_results)
        data_collector.append(data)
        data_collector_web.append(data_web)
        logging.info("")
    logging.info("GET daily papers end")

    if config["publish_readme"]:
        write_papers_split(
            data_collector,
            config["json_readme_path"],
            config["archive_readme_json_dir"],
        )
    if config["publish_gitpage"]:
        write_papers_split(
            data_collector_web,
            config["json_gitpage_path"],
            config["archive_gitpage_json_dir"],
        )


def cmd_render(config: dict) -> None:
    """Read the persisted JSON splits, render README/gitpage/archive markdown."""
    show_badge = config["show_badge"]
    user_name = config["user_name"]
    repo_name = config["repo_name"]

    if config["publish_readme"]:
        json_to_md(
            config["json_readme_path"],
            config["md_readme_path"],
            task="Update Readme",
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
            archive_index_link="docs/archive/index.md",
        )
        render_archive_pages(
            config["archive_readme_json_dir"],
            config["archive_readme_md_dir"],
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
        )

    if config["publish_gitpage"]:
        json_to_md(
            config["json_gitpage_path"],
            config["md_gitpage_path"],
            task="Update GitPage",
            to_web=True,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
            archive_index_link="archive-web/index.md",
        )
        render_archive_pages(
            config["archive_gitpage_json_dir"],
            config["archive_gitpage_md_dir"],
            to_web=True,
            show_badge=show_badge,
            user_name=user_name,
            repo_name=repo_name,
        )


def cmd_run(config: dict) -> None:
    """Full pipeline: fetch then render. The cron workflow calls this."""
    cmd_fetch(config)
    cmd_render(config)


def _parse_yyyy_mm(value: str) -> datetime.date:
    """`"2025-08"` → date(2025, 8, 1). Raises argparse-friendly ValueError."""
    try:
        year_str, month_str = value.split("-")
        return datetime.date(int(year_str), int(month_str), 1)
    except (ValueError, AttributeError) as e:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {value!r}") from e


def _iter_month_ranges(start: datetime.date, end: datetime.date) -> Iterator[tuple[datetime.date, datetime.date]]:
    """Yield (first_of_month, last_of_month) for every month in [start, end].
    Both bounds are normalized to the first of their month before iteration."""
    cur = datetime.date(start.year, start.month, 1)
    end_first = datetime.date(end.year, end.month, 1)
    while cur <= end_first:
        next_first = datetime.date(cur.year + 1, 1, 1) if cur.month == 12 else datetime.date(cur.year, cur.month + 1, 1)
        last = next_first - datetime.timedelta(days=1)
        yield cur, last
        cur = next_first


def cmd_backfill(
    config: dict,
    *,
    start: datetime.date,
    end: datetime.date,
    max_results: int = BACKFILL_DEFAULT_MAX_RESULTS,
) -> None:
    """Fetch every (keyword × month) in [start, end] and merge into the archive.

    Idempotent — the underlying `write_papers_split` re-buckets all known
    papers, so re-running over an already-populated range is safe.

    `max_results` controls per (keyword × month) cap. Defaults to the backfill-
    appropriate ceiling (NOT `config["max_results"]`, which is the daily-fetch
    cap of ~10 — far too low for a months-wide recovery).
    """
    keywords = config["kv"]

    data_collector = []
    data_collector_web = []

    months = list(_iter_month_ranges(start, end))
    logging.info(f"BACKFILL begin: {start.isoformat()} → {end.isoformat()} ({len(months)} months)")

    for month_start, month_end in months:
        logging.info(f"=== {month_start.strftime('%Y-%m')} ===")
        for topic, keyword in keywords.items():
            logging.info(f"Keyword: {topic}")
            papers = fetch_papers_in_range(
                query=keyword,
                start=month_start,
                end=month_end,
                max_results=max_results,
            )
            data, data_web = papers_to_legacy_rows(papers, topic)
            data_collector.append(data)
            data_collector_web.append(data_web)

    logging.info("BACKFILL fetch end — persisting JSON splits")
    if config["publish_readme"]:
        write_papers_split(
            data_collector,
            config["json_readme_path"],
            config["archive_readme_json_dir"],
        )
    if config["publish_gitpage"]:
        write_papers_split(
            data_collector_web,
            config["json_gitpage_path"],
            config["archive_gitpage_json_dir"],
        )

    logging.info("BACKFILL render begin")
    cmd_render(config)
    logging.info("BACKFILL done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nlp_arxiv_daily")
    parser.add_argument(
        "--config_path",
        type=str,
        default="config.yaml",
        help="configuration file path",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="fetch then render (default)")
    sub.add_parser("fetch", help="fetch arxiv + persist JSON splits")
    sub.add_parser("render", help="render persisted JSON to markdown")

    backfill = sub.add_parser("backfill", help="fetch a date range and merge into archive")
    backfill.add_argument(
        "--start",
        required=True,
        type=_parse_yyyy_mm,
        help="start month (inclusive), YYYY-MM",
    )
    backfill.add_argument(
        "--end",
        type=_parse_yyyy_mm,
        default=None,
        help="end month (inclusive), YYYY-MM (default: current month)",
    )
    backfill.add_argument(
        "--max-results",
        type=int,
        default=BACKFILL_DEFAULT_MAX_RESULTS,
        help=f"max results per (keyword × month) query (default: {BACKFILL_DEFAULT_MAX_RESULTS})",
    )
    return parser


def _current_month_first() -> datetime.date:
    today = datetime.date.today()
    return datetime.date(today.year, today.month, 1)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)
    command = args.command or "run"

    if command == "backfill":
        end = args.end if args.end is not None else _current_month_first()
        cmd_backfill(config, start=args.start, end=end, max_results=args.max_results)
        return 0

    # Resolve handler at call time so tests can monkeypatch cmd_* on this module.
    handler = {"run": cmd_run, "fetch": cmd_fetch, "render": cmd_render}[command]
    handler(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
