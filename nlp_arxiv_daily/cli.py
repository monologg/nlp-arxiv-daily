"""CLI subcommand dispatch for the nlp_arxiv_daily pipeline.

Three subcommands:
- `fetch`  — query arxiv per keyword, persist current/archive JSON splits.
- `render` — read the persisted JSON, write README/gitpage/archive markdown.
- `run`    — fetch then render (this is what the cron workflow calls).

JSON is the boundary between fetch and render, so the two subcommands can
also be run independently — useful for backfills and golden-output testing.
"""

from __future__ import annotations

import argparse
import logging
import sys

from nlp_arxiv_daily.core import get_daily_papers, load_config
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)
    # Resolve handler at call time so tests can monkeypatch cmd_* on this module.
    command = args.command or "run"
    handler = {"run": cmd_run, "fetch": cmd_fetch, "render": cmd_render}[command]
    handler(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
